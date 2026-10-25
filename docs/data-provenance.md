# Data provenance and fictional case

The canonical fixture is [CASE-SYN-104](../fixtures/case-syn-104.json), invoice
INV-SYN-4817: two blue mugs at GBP 12.50 each. A customer **reports** one red mug.
Fulfillment is unknown. Synthetic returns-v3 requires purchase and case checks
and never authorizes automatic refund. Purchase and case checks have not been
completed merely because an invoice or ticket is present.

Northstar Retail has Service Operations and Inventory Operations within one
tenant. Platform Engineering supports those units. Harbor Retail is another
fictional tenant. Tenant boundaries and unit/role grants are separate concepts.
Synthetic v4 requires an explicit scenario branch/reset; it is not a global
replacement for v3. The fixture's fixed teaching clock is synthetic too.

## Historical public data

[UCI Online Retail](https://archive.ics.uci.edu/dataset/352/online%2Bretail) is
historical transaction data from a different retailer. Its citation is Chen, D.
(2015), DOI [10.24432/C5BW33](https://doi.org/10.24432/C5BW33), CC BY 4.0.
It supplies no evidence for our synthetic tickets, tenants, policies, delivered
colors, or refund authority. The baseline includes no raw download or derived
UCI rows. [provenance.json](../data/provenance.json) records this explicitly;
unobserved checksums remain null, with a reason.

Before any future derivation: record source URL and retrieval time, archive and
workbook SHA-256, dataset version/date if supplied, transformation command and
code hash, stable row-selection rule, retained/removed fields, row counts,
missing-value handling, derived file SHA-256, attribution, and license. Keep
`CustomerID` out of all committed records. Do not treat pseudonymization as
permission to publish raw customer identifiers. Minimize invoice IDs and dates
too; document the necessity of every retained field. Keep full archives/workbooks
and raw identifiers under ignored local storage outside the publishable tree.

Provenance checks must reject a synthetic record labeled as UCI-derived and a
public data record without source/checksum/transformation lineage. Model outputs
and inferred graph edges are derived artifacts, not source evidence. Deleted
source content must not survive through a summary, embedding, trace, or graph.
