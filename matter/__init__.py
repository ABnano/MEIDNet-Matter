"""
MEIDNet Matter: crystal structures for a requested band gap, each with the evidence for it.

Ask for a band gap and get crystal structures back, each with two machine-learning readings of the PBE gap, its checks
and its limits. Matter reports what the data and the model support (the Design Readiness report), generates or
searches candidate structures and returns them with their evidence and provenance. The scientific engine is the ``meidnet`` package; Matter imports it and never
copies it.
"""

__version__ = "0.10.0"
