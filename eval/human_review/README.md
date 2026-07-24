# Human-review agreement sample

`eval/agreement_eval.py --review-file <this dir>/review_sample.csv` computes
Cohen's kappa between the Supervisor's `final_action` and a human reviewer's
judgment of whether each ticket should have been escalated.

Fill `review_template.csv` from real pipeline traces (ticket text, model
action, confidence), then have a reviewer set `human_would_escalate`.

## Process

1. Run tickets through the pipeline (UI or API) and sample from the DB.
2. For each ticket, add a row: `ticket_id`, `ticket_text`, `model_final_action`,
   `model_confidence` (from `/api/v1/tickets/{id}/trace`).
3. Reviewer fills `human_would_escalate` (`true`/`false`), ideally blind to the model decision.
4. Run `python eval/agreement_eval.py --review-file eval/human_review/review_sample.csv`.

Aim for at least 30–50 rows before relying on kappa.
