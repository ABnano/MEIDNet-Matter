# What happens to your data

## On the shared Space (babu09-meidnet-matter.hf.space)

* **What is sent.** In this version nothing is uploaded: a search sends the goal you set (targets, elements, rules, budget). The browser keeps a random per-tab session id so the server can list your runs.
* **What is stored.** A run folder on the container's disk: the goal, the engine's configuration, the candidates with their CIF files, the funnel, the manifest. It is removed after an hour without access and on every restart or redeploy of the Space. There is no database and no account.
* **What is never done.** Your inputs are not used to train anything, and they are not shared.
* **Logs.** The server's access log (request paths and the client address as forwarded by Hugging Face) is visible to the owner of the Space in its logs panel, as for any Space.
* **Who has access.** The owner of the Space; Hugging Face according to its terms.
* **Analytics.** None beyond the Space's own visit counter.

## Run it yourself

`pip install -e .` and `python -m uvicorn matter.app:app` run everything on your computer; nothing leaves it. `docs/deployment.md` has the commands.

## Labels

Predictions are model estimates and are labelled "Predicted". DFT values next to a candidate come from the Perov-5 dataset and are labelled "DFT-computed (Perov-5)". A composition is "Found in the Perov-5 dataset" or "Not found in the Perov-5 dataset", naming what was checked. Every candidate's stability stage is "Not screened" in this version.

## Phase 1

When uploading your own dataset arrives, this page will state the size caps, where the files are processed, and the same retention: removed after an hour of inactivity and on every restart, never reused.
