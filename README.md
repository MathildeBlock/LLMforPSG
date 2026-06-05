# LLMforPSG

Code repository for the master thesis *Adapting Large Language Models for Structured Information Extraction from Sleep Study Reports*.

This repository contains the main scripts used for preprocessing PSG reports, constructing prompts, running local LLM inference, post-processing extracted JSON outputs, and comparing experiment results.

Clinical report data, manually annotated reference files, generated model outputs, and Jupyter notebooks containing non-shareable information are not included for privacy reasons.

## Contents

- `psg_preprocess.py`: conversion and text extraction from historical Word reports.
- `psg_extractPL.py`: local LLM inference pipeline.
- `prompts.py`: prompt variants used in the experiments.
- `run_queue.py`: experiment queue for model/prompt runs.
- `psg_post.py`: post-processing and schema harmonisation.
- `compare_experiments.py`: evaluation and comparison of experiment outputs.

## Note

The code is provided for transparency and reproducibility of the thesis methodology. It cannot be run end-to-end without access to the private clinical report archive, reference annotations, and local model environment.
