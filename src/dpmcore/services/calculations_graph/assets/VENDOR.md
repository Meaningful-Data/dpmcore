# Vendored JavaScript for the calculations graph

The `dpmcore generate-graph` command embeds these libraries **inline** in the
generated HTML so the file opens offline, with no network access. They are
vendored here (rather than loaded from a CDN) for exactly that reason.

All three libraries are MIT-licensed, which permits redistribution provided the
copyright/permission notice is retained — the notices are kept inside the
minified files themselves.

| File | Library | Version | License | Source |
| --- | --- | --- | --- | --- |
| `cytoscape.min.js` | [Cytoscape.js](https://js.cytoscape.org/) | 3.30.2 | MIT | <https://cdn.jsdelivr.net/npm/cytoscape@3.30.2/dist/cytoscape.min.js> |
| `dagre.min.js` | [dagre](https://github.com/dagrejs/dagre) | 0.8.5 | MIT | <https://cdn.jsdelivr.net/npm/dagre@0.8.5/dist/dagre.min.js> |
| `cytoscape-dagre.min.js` | [cytoscape-dagre](https://github.com/cytoscape/cytoscape.js-dagre) | 2.5.0 | MIT | <https://cdn.jsdelivr.net/npm/cytoscape-dagre@2.5.0/cytoscape-dagre.min.js> |

`cytoscape-dagre.min.js` is a minified webpack UMD bundle that carries no
embedded version string; 2.5.0 is the release compatible with Cytoscape 3.30
and dagre 0.8.5. Confirm the version when updating.

## Updating

Re-download the pinned versions (bump the version numbers first if upgrading)
and overwrite the files in place. From the repository root:

```bash
cd src/dpmcore/services/calculations_graph/assets
curl -fsSL -o cytoscape.min.js       https://cdn.jsdelivr.net/npm/cytoscape@3.30.2/dist/cytoscape.min.js
curl -fsSL -o dagre.min.js           https://cdn.jsdelivr.net/npm/dagre@0.8.5/dist/dagre.min.js
curl -fsSL -o cytoscape-dagre.min.js https://cdn.jsdelivr.net/npm/cytoscape-dagre@2.5.0/cytoscape-dagre.min.js
```

After updating, regenerate a graph and open it offline to confirm the layout
still renders, then update the version numbers in this file. The filenames are
referenced by `CalculationsGraphService._ASSET_FILES` in `../service.py`; keep
them in sync if a filename changes.
