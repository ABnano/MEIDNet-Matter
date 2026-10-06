# Data format (Phase 1, coming next)

This version does not take uploads. The layout below is what Phase 1 will read; it is the layout the engine already accepts (`meidnet check`).

## A table with a CIF column

A CSV or Excel file with one row per material:

| column | content |
|---|---|
| `material_id` | a unique id (any text) |
| `cif` | the structure as CIF text |
| one column per property | a number; the unit is given when the columns are mapped |

## A table and a folder of CIF files

A ZIP with `properties.csv` (`material_id` and the property columns) and `structures/<material_id>.cif`.

## What Matter will report after reading it

The number of rows, the usable structures, the properties detected and their distributions, missing values, duplicated ids, equivalent structures, malformed CIFs, cells with more than the model's site limit, partially occupied sites, elements present, and which family prototype the cells match. Every excluded row comes with its reason, in a downloadable table; nothing is cleaned silently.

## Caps on the shared Space

Phase 1 will state them here (rows, CIF size, archive size, training epochs and time); locally there are none.
