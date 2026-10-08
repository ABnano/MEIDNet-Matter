"""
MEIDNet — Multimodal Equivariant Inverse Design Network
=======================================================

Learn a shared latent space between crystal structures and their properties,
then search it for new materials that hit property targets while obeying the
chemical and structural rules of a material family.

Typical use (the same steps the ``meidnet`` command runs)::

    from meidnet.config import load_config
    from meidnet.pipeline import check, train, generate

    cfg = load_config("meidnet.yaml")
    check(cfg)        # is my data usable?  (writes check_report.html)
    train(cfg)        # learn the latent space (writes model.pt + training_report.html)
    generate(cfg)     # design candidates (writes CIFs + generation_report.html)
"""

__version__ = "2.4.0.dev2"
