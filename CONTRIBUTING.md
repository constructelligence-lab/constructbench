# Contributing to ConstructBench

The most useful contributions are **new task families**, **harder tiers**, and **results** from models we have not run.

## Add a task family

1. Write `fn(rng, i) -> Task` in `constructbench/generators/`. Compute the answer **in code from the same numbers** that appear in
   the prompt. Never hand-key an answer.
2. State every convention in the prompt (rounding, units, calendar, which rule applies) so there is exactly one right answer.
   If a competent practitioner could reasonably answer differently, the task is not ready.
3. Register it in `registry.FAMILIES`.
4. Add a test. The suite already checks that the oracle provider scores 100% on every family, and several tests re-derive the
   answer from the prompt text. Run one file at a time (`python -m unittest discover -s tests -p test_yourfile.py`); the whole
   suite can use a lot of memory on a small machine.
5. Say in the pull request who would care about this task in real work.

## Add a result

Open a pull request with the run file, the exact command, the model and settings, and the task set and seed. Incomplete runs are
fine: they are reported as not run. Do not pick the seed after looking at scores.

## Rules of the house

- **Honest over impressive.** Report what failed. A family that turns out too easy or ambiguous is a finding, not an embarrassment.
- **No contamination.** Do not add a task whose answer is in a public document the models trained on, without saying so.
- **Held-out sets stay private.** Do not commit them. Generate your own with a seed you keep to yourself.
- **No confidential project data** in examples or prompts.
- By contributing you agree your work is released under the repository licence (MIT).

See also the [code of conduct](CODE_OF_CONDUCT.md).
