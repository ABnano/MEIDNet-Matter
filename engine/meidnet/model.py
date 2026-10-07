"""
The MEIDNet network: two encoders, two decoders and a shared latent space.

    crystal  ──SE3Encoder──► z_c ─┐                        ┌─► SE3Decoder   ──► crystal
                                  ├─ shared latent space ──┤
    properties ─PropertyEncoder─► z_p ─┘  (CLIP alignment)  └─► PropertyDecoder ─► properties

Both encoders project into the same space and are pulled together by a
contrastive (InfoNCE) loss, so a latent made from target *properties* can be
decoded into a *structure*.  Layer names, shapes and the order in which layers
are created are kept identical to MEIDNet v1, so published checkpoints load and
give bit-identical outputs; the only generalisation is that the property
modality may have any number of properties.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from meidnet.chem import NUM_SPECIES
from meidnet.data import split_dense


def element_table(kind: str):
    """(118, d) fixed element-descriptor matrix: row Z-1 describes element Z.  'cgcnn' = the 92 CGCNN atom features
    (group, period, electronegativity, radius, valence, ionisation energy, ... ; Xie & Grossman 2018) for Z = 1..100,
    zeros above.  Lets the model represent elements it never saw in training through their chemistry."""
    import json, os
    feats = json.load(open(os.path.join(os.path.dirname(__file__), "element_features_cgcnn.json")))
    d = len(next(iter(feats.values())))
    table = torch.zeros(NUM_SPECIES, d)
    for z, v in feats.items():
        if 1 <= int(z) <= NUM_SPECIES:
            table[int(z) - 1] = torch.tensor(v, dtype=torch.float32)
    return table


class EGNNLayer(nn.Module):
    """E(n)-equivariant message passing on squared inter-atomic distances (Satorras et al. 2021)."""

    def __init__(self, node_dim, edge_dim, periodic=False):
        super().__init__()
        self.periodic = periodic
        self.phi_e = nn.Sequential(nn.Linear(2 * node_dim + 1, edge_dim), nn.ReLU(), nn.Linear(edge_dim, edge_dim))
        self.phi_x = nn.Sequential(nn.Linear(edge_dim, 1))
        self.phi_h = nn.Sequential(nn.Linear(node_dim + edge_dim, node_dim), nn.ReLU())

    def forward(self, h, x, adj):
        B, N, _ = h.shape
        diff = x.unsqueeze(2) - x.unsqueeze(1)
        if self.periodic:                     # fractional coordinates: minimum-image convention
            diff = diff - torch.round(diff)
        dist2 = (diff ** 2).sum(dim=-1, keepdim=True)
        h_i = h.unsqueeze(2).expand(B, N, N, h.size(-1))
        h_j = h.unsqueeze(1).expand(B, N, N, h.size(-1))
        edge = self.phi_e(torch.cat([h_i, h_j, dist2], dim=-1))
        edge = edge * adj.unsqueeze(-1)
        x_new = x + (diff * self.phi_x(edge)).sum(dim=2)
        h_new = self.phi_h(torch.cat([h, edge.sum(dim=2)], dim=-1))
        return h_new, x_new


class SE3Encoder(nn.Module):
    """Crystal → latent.  Embeds elements, runs two EGNN layers, pools atoms, adds the lattice."""

    def __init__(self, max_sites, num_species, latent_dim, node_hidden_dim=128, species_embedding_dim=64, edge_dim=64,
                 periodic=False, element_features="onehot"):
        super().__init__()
        self.max_sites = max_sites
        self.num_species = num_species
        self.element_features = element_features
        if element_features == "onehot":
            self.species_embedding = nn.Linear(num_species, species_embedding_dim)
        else:                                    # element descriptors: unseen elements are embedded through their chemistry
            self.register_buffer("element_table", element_table(element_features))
            self.species_embedding = nn.Linear(self.element_table.shape[1], species_embedding_dim)
        self.init_node_fc = nn.Sequential(nn.Linear(species_embedding_dim, node_hidden_dim), nn.ReLU())
        self.egnn1 = EGNNLayer(node_hidden_dim, edge_dim, periodic)
        self.egnn2 = EGNNLayer(node_hidden_dim, edge_dim, periodic)
        self.aggregate_fc = nn.Sequential(nn.Linear(node_hidden_dim, 128), nn.ReLU())
        self.lat_fc = nn.Sequential(nn.Linear(6, 64), nn.ReLU())
        self.comb_fc = nn.Sequential(nn.Linear(64 + 128, 128), nn.ReLU())
        self.fc_mu = nn.Linear(128, latent_dim)

    def forward(self, x):
        comp = split_dense(x, self.max_sites)
        lat, adj, species, coords = comp["lat"], comp["adj"], comp["species"], comp["coords"]
        lat_emb = self.lat_fc(lat)
        if self.element_features != "onehot":
            species_in = species @ self.element_table
        else:
            species_in = species
        h = self.init_node_fc(self.species_embedding(species_in))
        mask = (species.sum(dim=-1) > 0).float().unsqueeze(-1)
        center = (coords * mask).sum(dim=1) / (mask.sum(dim=1) + 1e-8)
        h, xc = self.egnn1(h, coords - center.unsqueeze(1), adj)
        h, xc = self.egnn2(h, xc, adj)
        h = h * mask
        agg = self.aggregate_fc(h.sum(dim=1) / (mask.sum(dim=1).clamp(min=1)))
        z = self.fc_mu(self.comb_fc(torch.cat([lat_emb, agg], dim=-1)))
        return z, center


class SE3Decoder(nn.Module):
    """Latent → lattice, per-site element scores, positions and adjacency."""

    def __init__(self, max_sites, num_species, latent_dim, node_hidden_dim=128, edge_dim=64, element_features="onehot"):
        super().__init__()
        self.max_sites = max_sites
        self.num_species = num_species
        self.fc_lat = nn.Sequential(nn.Linear(latent_dim, 64), nn.ReLU(), nn.Linear(64, 6))
        self.fc_nodes = nn.Sequential(nn.Linear(latent_dim, max_sites * node_hidden_dim), nn.ReLU())
        self.egnn1 = EGNNLayer(node_hidden_dim, edge_dim)
        self.egnn2 = EGNNLayer(node_hidden_dim, edge_dim)
        self.fc_species_decoded = nn.Sequential(nn.Linear(node_hidden_dim, 64), nn.ReLU())
        self.element_features = element_features
        if element_features == "onehot":
            self.fc_species_final = nn.Linear(64, num_species)
        else:                                    # score every element by similarity of its descriptor to the site state
            self.register_buffer("element_table", element_table(element_features))
            self.fc_species_final = nn.Linear(64, self.element_table.shape[1])
        self.fc_coords = nn.Sequential(nn.Linear(node_hidden_dim, 3))

    def add_symmetry_head(self, n_spacegroups=230, max_orbits=16, latent_dim=128, hidden=256):
        """The D1 geometry head: a crystal as a space group plus the few sites that symmetry does NOT relate.

        The free-coordinate head has to place every atom and fails (on MP-20 the cells it emits have a median volume per
        atom of 0.0 A^3 and 81% contain atoms closer than 0.7 A).  A conventional cell holds a median of 16 atoms but only
        a median of **4** symmetry-distinct sites, so predicting the space group and those few sites is a far smaller
        problem, and the symmetry operations generate the rest.

        Deliberately NOT a prototype classifier: the space group, the site species and their free coordinates are
        predicted separately, so a combination absent from training can still be produced.  Predicting one of the
        thousands of known prototypes would buy validity at the cost of only ever reproducing known structure types.
        Added as a separate method so a checkpoint trained without it loads unchanged.
        """
        self.max_orbits = max_orbits
        self.sym_trunk = nn.Sequential(nn.Linear(latent_dim, hidden), nn.SiLU(), nn.Linear(hidden, hidden), nn.SiLU())
        self.fc_spacegroup = nn.Linear(hidden, n_spacegroups)
        self.fc_orbit = nn.Sequential(nn.Linear(hidden, max_orbits * 64), nn.SiLU())
        self.fc_orbit_occupied = nn.Linear(64, 1)                      # is this orbit used at all
        self.fc_orbit_species = nn.Linear(64, self.num_species)
        self.fc_orbit_coords = nn.Linear(64, 3)
        self.fc_sym_lattice = nn.Sequential(nn.Linear(hidden, 64), nn.SiLU(), nn.Linear(64, 6))
        return self

    def symmetry_forward(self, z):
        """(space-group logits, occupancy logits, species logits, fractional coordinates, lattice) for the D1 head."""
        t = self.sym_trunk(z)
        o = self.fc_orbit(t).view(z.size(0), self.max_orbits, 64)
        return (self.fc_spacegroup(t),
                self.fc_orbit_occupied(o).squeeze(-1),
                self.fc_orbit_species(o),
                torch.sigmoid(self.fc_orbit_coords(o)),                # fractional, so bounded to [0, 1)
                self.fc_sym_lattice(t))

    def add_coordinate_bins(self, n_bins=48):
        """Predict each fractional coordinate as one of `n_bins` discrete values instead of regressing it.

        This is a measured decision, not a preference.  Representative coordinates are strongly multimodal: of the
        120,120 components in MP-20's validation split, 35,882 sit at 0 and 21,415 at 1/2, and 59% are exactly one of
        twelve simple fractions.  An MSE regression onto a multimodal target converges on the conditional *mean*, which
        falls between the modes -- the regression head reached 0.242 RMSE where predicting one global constant scores
        0.300, so it was only 19% better than a constant, and it did not improve between 3 and 100 epochs.
        Cross-entropy over a grid selects the mode instead, which is what WyCryst and DiffCSP++ rely on.

        Grid points are i/n_bins, so at n_bins=48 the values 0, 1/8, 1/6, 1/4, 1/3, 3/8, 1/2, 5/8, 2/3, 3/4, 5/6 and
        7/8 are all exact grid points, and anything else is quantised by at most 1/96 = 0.010 -- inside the 0.02 the
        symmetry expansion needs (measured: 100% correct cells at 0.01 error, 91% at 0.02).

        Kept as a separate method so a D1 checkpoint trained before this existed still loads unchanged.
        """
        self.n_coord_bins = n_bins
        self.fc_orbit_coord_bins = nn.Linear(64, 3 * n_bins)
        return self

    def coordinate_bin_logits(self, z):
        """(B, max_orbits, 3, n_bins) logits over the discrete coordinate grid."""
        o = self.fc_orbit(self.sym_trunk(z)).view(z.size(0), self.max_orbits, 64)
        return self.fc_orbit_coord_bins(o).view(z.size(0), self.max_orbits, 3, self.n_coord_bins)

    def forward(self, z, input_coords=None, center=None, species_mask=None):
        B, N = z.size(0), self.max_sites
        lat_out = self.fc_lat(z)
        nodes = self.fc_nodes(z).view(B, N, -1)
        if input_coords is None:
            input_coords = torch.zeros(B, N, 3, device=z.device)
        if center is None:
            center = torch.zeros(B, 3, device=z.device)
        full_adj = torch.ones(B, N, N, device=z.device)
        h, xc = self.egnn1(nodes, input_coords - center.unsqueeze(1), full_adj)
        h, xc = self.egnn2(h, xc, full_adj)
        species_logits = self.fc_species_final(self.fc_species_decoded(h))
        if self.element_features != "onehot":
            species_logits = species_logits @ self.element_table.T
        if species_mask is not None:
            keep = species_mask.to(dtype=torch.bool, device=species_logits.device).unsqueeze(0)
            species_logits = species_logits.masked_fill(~keep, torch.finfo(species_logits.dtype).min)
        coords_out = self.fc_coords(h) + center.unsqueeze(1)
        adj_logits = torch.bmm(h, h.transpose(1, 2))
        return lat_out, adj_logits, species_logits, coords_out


class PropertyEncoder(nn.Module):
    """Property vector (normalised, in model column order) → latent."""

    def __init__(self, n_properties=2, hidden_dim=128, latent_dim=128):
        super().__init__()
        self.fc = nn.Sequential(nn.Linear(n_properties, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, latent_dim))

    def forward(self, x):
        return self.fc(x)


class PropertyDecoder(nn.Module):
    """Latent → property vector (normalised, in model column order)."""

    def __init__(self, latent_dim=128, n_properties=2):
        super().__init__()
        self.fc = nn.Sequential(nn.Linear(latent_dim, 64), nn.ReLU(), nn.Linear(64, n_properties))

    def forward(self, z):
        return self.fc(z)


class DualAutoencoderModel(nn.Module):
    def __init__(self, n_properties=2, max_sites=20, latent_dim=128, node_hidden_dim=128,
                 species_embedding_dim=64, edge_dim=64, property_hidden_dim=128, periodic_encoder=False,
                 element_features="onehot"):
        super().__init__()
        self.max_sites = max_sites
        self.num_species = NUM_SPECIES
        self.n_properties = n_properties
        self.latent_dim = latent_dim
        # creation order matters for reproducible initialisation (same as v1)
        self.crystal_encoder = SE3Encoder(max_sites, NUM_SPECIES, latent_dim, node_hidden_dim,
                                          species_embedding_dim, edge_dim, periodic=periodic_encoder,
                                          element_features=element_features)
        self.crystal_decoder = SE3Decoder(max_sites, NUM_SPECIES, latent_dim, node_hidden_dim, edge_dim,
                                          element_features=element_features)
        self.property_encoder = PropertyEncoder(n_properties, property_hidden_dim, latent_dim)
        self.property_decoder = PropertyDecoder(latent_dim, n_properties)
        self.proj_crystal = nn.Sequential(nn.Linear(latent_dim, latent_dim), nn.ReLU(), nn.Linear(latent_dim, latent_dim))
        self.proj_prop = nn.Sequential(nn.Linear(latent_dim, latent_dim), nn.ReLU(), nn.Linear(latent_dim, latent_dim))

    # ── encoders ─────────────────────────────────────────────────────────────
    def encode_crystal(self, crystal_vec):
        z_raw, center = self.crystal_encoder(crystal_vec)
        return F.normalize(self.proj_crystal(F.normalize(z_raw, p=2, dim=1)), p=2, dim=1), center

    def encode_properties(self, props):
        return F.normalize(self.proj_prop(F.normalize(self.property_encoder(props), p=2, dim=1)), p=2, dim=1)

    def encode_modalities(self, crystal_vec, props):
        """Returns z_c, z_p, z_joint = (z_c + z_p)/2, the encoder's centre, input species and coordinates."""
        z_c, center = self.encode_crystal(crystal_vec)
        z_p = self.encode_properties(props)
        z_joint = (z_c + z_p) / 2.0
        comp = split_dense(crystal_vec, self.max_sites)
        return z_c, z_p, z_joint, center, comp["species"], comp["coords"]

    def forward(self, crystal_vec, props, coords=None, center=None):
        """Training forward pass: decode crystal and properties from the joint latent."""
        z_c, z_p, z_joint, enc_center, _, data_coords = self.encode_modalities(crystal_vec, props)
        lat, adj, spc, crd = self.crystal_decoder(
            z_joint,
            input_coords=data_coords if coords is None else coords,
            center=enc_center if center is None else center,
        )
        return z_c, z_p, lat, adj, spc, crd, self.property_decoder(z_joint)
