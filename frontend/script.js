/* ===================================================================
   Backend — all pricing math now lives server-side in calculator.py.
   Update this once the API is deployed (Render/Railway, etc).
   =================================================================== */
const API_BASE_URL = "http://localhost:8000";

/* ---------- Elements ---------- */
const pageInput = document.getElementById("page-input");
const pageAnalyzing = document.getElementById("page-analyzing");
const pageWeight = document.getElementById("page-weight");
const pageResult = document.getElementById("page-result");

const productLinkInput = document.getElementById("productLink");
const analyzeBtn = document.getElementById("analyzeBtn");
const linkError = document.getElementById("linkError");
const newSearchBtn = document.getElementById("newSearchBtn");

const weightInput = document.getElementById("weightInput");
const submitWeightBtn = document.getElementById("submitWeightBtn");
const weightError = document.getElementById("weightError");
const cancelWeightBtn = document.getElementById("cancelWeightBtn");

// Remembers the link between the first call (which may come back
// needsWeight: true) and the follow-up call that includes the weight.
let pendingUrl = null;

/* ---------- Store detection ---------- */
function detectStore(url){
  try{
    const host = new URL(url).hostname.replace(/^www\./, "");
    if (host.includes("stylekorean")) return "style_korean";
    if (host.includes("yesstyle")) return "yes_style";
    return null;
  } catch {
    return null;
  }
}

/* ---------- Extraction + pricing — both now happen on the backend ----------
   The API reads the page, extracts the product fields, runs the pricing
   formulas server-side, and returns only the final total. The browser
   never sees DOLLAR_RATE, shipping cost, service fee, or margin.
------------------------------------------------------------------- */
async function analyzeLink(url, weight){
  const body = weight != null ? { url, weight } : { url };

  const res = await fetch(`${API_BASE_URL}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });

  if (!res.ok){
    const errBody = await res.json().catch(() => ({}));
    throw new Error(errBody.detail || "Couldn't analyze that link.");
  }

  return res.json(); // { store, productName, price, weight, timeDeal, eligibleForCode, totalEGP, needsWeight }
}

/* ---------- Page transitions ---------- */
function showPage(page){
  [pageInput, pageAnalyzing, pageWeight, pageResult].forEach(p => p.classList.remove("is-active"));
  page.classList.add("is-active");
}

/* ---------- Render result ---------- */
function renderResult(data){
  document.getElementById("outProductName").textContent = data.productName;
  document.getElementById("outStore").textContent =
    data.store === "style_korean" ? "StyleKorean" : "YesStyle";
  document.getElementById("outTimeDeal").textContent =
    data.store === "style_korean"
      ? (data.timeDeal ? "Yes" : "No")
      : (data.eligibleForCode ? "Eligible for code" : "Not eligible");
  document.getElementById("outPrice").textContent = "$" + data.price.toLocaleString();
  document.getElementById("outWeight").textContent = data.weight.toLocaleString() + " g";
  document.getElementById("outTotalEGP").textContent =
    Math.round(data.totalEGP).toLocaleString() + " EGP";
}

/* ---------- Main flow ---------- */
async function handleAnalyze(){
  const url = productLinkInput.value.trim();
  linkError.textContent = "";

  const store = detectStore(url);
  if (!url || !store){
    linkError.textContent = "Paste a valid StyleKorean or YesStyle product link.";
    return;
  }

  pendingUrl = url;
  analyzeBtn.disabled = true;
  showPage(pageAnalyzing);

  try{
    const [data] = await Promise.all([
      analyzeLink(url),
      new Promise(resolve => runAnalyzingAnimation(resolve))
    ]);

    if (data.needsWeight){
      weightInput.value = "";
      weightError.textContent = "";
      showPage(pageWeight);
    } else {
      renderResult(data);
      showPage(pageResult);
    }
  } catch (err){
    showPage(pageInput);
    linkError.textContent = err.message || "Something went wrong reading that link. Please try again.";
  } finally {
    analyzeBtn.disabled = false;
  }
}

/* ---------- Weight follow-up (YesStyle) ---------- */
async function handleSubmitWeight(){
  const weight = parseFloat(weightInput.value);
  weightError.textContent = "";

  if (!weight || weight <= 0){
    weightError.textContent = "Enter the product's weight in grams.";
    return;
  }

  submitWeightBtn.disabled = true;
  showPage(pageAnalyzing);

  try{
    const [data] = await Promise.all([
      analyzeLink(pendingUrl, weight),
      new Promise(resolve => runAnalyzingAnimation(resolve))
    ]);

    if (data.needsWeight){
      // Shouldn't happen once a weight is supplied, but don't strand the user.
      weightError.textContent = "Still couldn't price that — try re-entering the weight.";
      showPage(pageWeight);
    } else {
      renderResult(data);
      showPage(pageResult);
    }
  } catch (err){
    showPage(pageWeight);
    weightError.textContent = err.message || "Something went wrong. Please try again.";
  } finally {
    submitWeightBtn.disabled = false;
  }
}

analyzeBtn.addEventListener("click", handleAnalyze);
submitWeightBtn.addEventListener("click", handleSubmitWeight);

cancelWeightBtn.addEventListener("click", () => {
  pendingUrl = null;
  productLinkInput.value = "";
  linkError.textContent = "";
  showPage(pageInput);
});

newSearchBtn.addEventListener("click", () => {
  pendingUrl = null;
  productLinkInput.value = "";
  linkError.textContent = "";
  showPage(pageInput);
});