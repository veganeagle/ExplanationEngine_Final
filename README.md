# Explanation Engine

## Overview
This application evaluates candidate resumes against a job description using multiple ranking methods (TF-IDF, BM25, Transformer) and generates explanation factors based on experimental perturbations.

## Requirements

- Python 3.10+
- Ollama installed and running

## Setup

1. Install Ollama from the official site
2. Pull the required model:

   ollama pull llama3.2:3b

3. Run setup:

   setup.bat

## Run the Application

run.bat

Then open:

http://127.0.0.1:8000/

## Demo Workflow

1. Create or load a job
2. Attach candidates (from provided Job_Packs or upload)
3. Run baseline
4. Run experiment
5. View explanation results

## Notes

- The application runs locally only
- Ollama must be running before starting the app
- Initial runs may take longer depending on model performance