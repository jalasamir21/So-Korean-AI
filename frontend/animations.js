/* ===================================================================
   Analyzing-steps animation
   Plays the four checklist steps one by one, then calls onComplete.
   Kept separate from script.js so the calculation/API logic stays
   easy to find on its own.
   =================================================================== */

const STEP_DELAY_MS = 550;
const FINAL_PAUSE_MS = 350;

function runAnalyzingAnimation(onComplete){
  const steps = Array.from(document.querySelectorAll("#analyzingSteps li"));

  // reset state in case this runs more than once
  steps.forEach(step => step.classList.remove("is-active", "is-done"));

  let i = 0;

  function playNext(){
    if (i > 0){
      steps[i - 1].classList.remove("is-active");
      steps[i - 1].classList.add("is-done");
    }

    if (i < steps.length){
      steps[i].classList.add("is-active");
      i++;
      setTimeout(playNext, STEP_DELAY_MS);
    } else {
      setTimeout(onComplete, FINAL_PAUSE_MS);
    }
  }

  playNext();
}