# MEIDNet Matter

**From your materials data to candidate structures.**

MEIDNet Matter is a multimodal inverse-design workbench for crystalline materials. A researcher brings crystal structures and properties; Matter reports what the data and the model support (the Design Readiness report), then runs a constrained, property-conditioned search and returns candidate structures with their evidence and provenance. The scientific engine is [MEIDNet](https://github.com/ABnano/MEIDNet); Matter imports it as a package.

Matter currently searches property-conditioned candidates within supported structural families. Free-geometry crystal generation is planned as additional design backends mature.

This repository is under construction: Phase 0, the Perov-5 demo project end to end, is being built. The sibling platform [MEIDNet Prism](https://babu09-meidnet.hf.space/) is the place to learn the method, reproduce the results and benchmark models.

## Run the API

```bash
pip install -e ".[dev]"
python scripts/fetch_assets.py        # the model files, with checksums
python -m uvicorn matter.app:app --port 8000
```

`/health` answers at once; `/docs` is the API reference. The web app is built from `frontend/`.

## Licence

MIT. Author: Anand Babu.
