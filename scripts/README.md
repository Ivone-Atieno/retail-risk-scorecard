# scripts/

Step scripts in the order they were run in Google Colab. They share variables inside one Colab session, so they are a record of the work and not a stand-alone program. Reproduce the final results with `pipeline/`, `test/` and `sql/`.

- `01_design_phase/`: data extraction, cleaning, features, design score and validation (steps 1 to 19)
- `02_heldout_selection/`: choice of failed companies and controls, filing checks, protocol drafts (steps 20 to 42)
