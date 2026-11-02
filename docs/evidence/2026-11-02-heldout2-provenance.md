# heldout2 Step 6 — provenance and reproducibility

Provenance of the two `heldout2` runs reported in `2026-11-02-heldout2-report.md`.
The raw run records and logs are not published in this repository. They are
kept unchanged by the Workstream 3 owner, outside the repository, and can be
checked against the SHA-256 values below.

## Runs

| Item | Run 1 | Run 2 |
|---|---|---|
| GitHub Actions run (attempt) | 41355191796 (1) | 41373722509 (1) |
| Job | 124993637412 | 125049393823 |
| Mode, label | `fresh`, `run1` | `fresh`, `run2` |
| Workflow commit (`main`) | `6bfb6e6771d3b8d0915678eabe4f42242fd81f16` | `e42443bc176266fe047812ed8ca5aa20f0092758` |
| Time | 2026-11-01 22:03:58 to 23:18:16 UTC | 2026-11-02 01:40:39 to 03:05:37 UTC |
| Evaluation step | 1 h 12 min 48 s | 1 h 23 min 43 s |
| Runner | `ubuntu-24.04`, image ubuntu24/20261026.354.1, 4 vCPU AMD EPYC 9V74 80-Core Processor, 15.61 GiB | `ubuntu-24.04`, image ubuntu24/20261026.354.1, 4 vCPU AMD EPYC 7763 64-Core Processor, 15.61 GiB |
| Run status | 37/37 recorded, exit 0, complete=True | 37/37 recorded, exit 0, complete=True |
| Artifact | `heldout2-d4eacbf-run1`, id 13104753843, 103,848 bytes | `heldout2-d4eacbf-run2`, id 13112553650, 103,467 bytes |
| Artifact SHA-256 | `7d10dbcfb172f46e54b0c7a8452e593ed0cd95a55760fb8ca7dc663381742133` | `b673efde5286fe09a498a2db4690a16dc1335405d134d26c8fcbf4558ad40103` |
| Artifact expiry on GitHub | 2026-11-04 23:18 UTC | 2026-11-05 03:05 UTC |

## Identical configuration in both runs

- Evaluated code `d4eacbf0bd9626fe2b15a61a18d246ff9dd6e260`; cases and data frozen at `0b4030ec56ff71e5862ff78c6a8558114616a0ab` (handoff §8.1 checksums verified in each run).
- Python 3.13.17, `mcp` 2.2.0; identical `pip freeze` in both runs:
  `annotated-types==0.8.0`, `anyio==4.16.0`, `attrs==26.1.0`, `cffi==2.1.1`, `click==8.5.0`, `cryptography==50.0.2`, `h11==0.16.0`, `httpcore2==2.16.0`, `httpx2==2.16.0`, `idna==3.20`, `iniconfig==2.3.1`, `jsonschema==4.26.0`, `jsonschema-specifications==2025.9.1`, `mcp==2.2.0`, `mcp-types==2.2.0`, `opentelemetry-api==1.45.2`, `packaging==26.3`, `pluggy==1.7.0`, `pycparser==3.12`, `pydantic==2.14.2`, `pydantic_core==2.50.2`, `Pygments==2.21.0`, `PyJWT==2.15.1`, `pytest==9.2.0`, `python-multipart==0.0.33`, `referencing==0.37.0`, `rpds-py==2026.9.1`, `sse-starlette==3.6.0`, `starlette==1.10.0`, `truststore==0.10.5`, `typing-inspection==0.4.4`, `typing_extensions==4.16.0`, `uvicorn==0.54.0`.
- Ollama 0.40.6, release asset `ollama-linux-amd64.tar.zst` SHA-256 `c164ab8b1b28e2a247c29719b8e404c423c5b83ae64c3ab4e59d50c7ff7fc5e0`.
- Model `qwen3:8b`; registry manifest `sha256:500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`, config `sha256:05a61d37b08453e59290add468e3bb2f688e23a01e967fecb0e2fa41218cea76`; local manifest layers:
  - `application/vnd.ollama.image.model` `sha256:a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f` (5,225,374,496 bytes)
  - `application/vnd.ollama.image.template` `sha256:ae370d884f108d16e7cc8fd5259ebc5773a0afa6e078b11f4ed7e39a27e0dfc4` (1,723 bytes)
  - `application/vnd.ollama.image.license` `sha256:d18a5cc71b84bc4af394a31116bd3932b42241de70c77d2b76d69a314ec8aa12` (11,338 bytes)
  - `application/vnd.ollama.image.params` `sha256:cff3f395ef3756ab63e58b0ad1b32bb6f802905cae1472e6a12034e4246fbbdb` (120 bytes)
  - `application/vnd.docker.distribution.manifest.v2+json` `sha256:500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41` (859 bytes)
- `run_eval.py` arguments: `--dataset heldout2 --model qwen3:8b --no-think --num-ctx 4096 --timeout 900 --num-predict 768`; temperature 0 (code default); every check on.
- Ollama server: `OLLAMA_CONTEXT_LENGTH=4096`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`.
- Offline tests of the evaluated code before each run: 428 passed, 1 skipped.

## Checksums of the retained raw files

SHA-256 of every file of each artifact (37 case records, `summary.json`, `summary.md`, and `_meta/`).

### run1

```
e086463629e3f00283f6ec6206129a8ecd7ddfd1c1874425d9178de306fdf9fe  _meta/environment.json
b3d9ba7c899cfd112df2574c6a91458a70b724c5e4e50dfffd75574b2d1648e7  _meta/model-manifest.json
6671f32de01dcdf15ebb7e67be72b860647fa5926dbcf0c1bea7eb91b54f9d40  _meta/ollama-pull.log
465fa8995b416659d4dc3dc6ea3d78ae342181a0514884c06b0839b42bf10a2f  _meta/ollama-server.log
dca163f4bd8e4ad3f58f87d6cae77fef9d2d16fd8834450e4bfe2c08844b9e26  _meta/ollama-version.json
5e8cf0cade230c3c5673227781766a6e14c63c949f2b190f3efd81523efc7994  _meta/pip-freeze.txt
7c1a306170343576853fe6b4690bb6e9d60b1c9fd6bc7438a50d3a3272f8a00a  _meta/pytest.log
500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41  _meta/registry-manifest.json
111ec63f0b1111ce2eb3bedf953788a5d3e4d772e01f3eb9138232dd1d530bcb  _meta/run-status.json
39f429b28bd00d608b8db89064d0866defe63094813b7f842d5dfb7dab242889  _meta/run_eval.log
e408a163b190d37f6b8ccb7baba85bb434fee13f616d842b6e8c6405b5de5d54  N01.json
075a27a99149f3d07b39cc3b2b520e181e4797006502d635a8cbf7f84432343a  N02.json
07575b3ae29a8eafb1cc93829240f9ca1f9617f55d50a02506407e58e6a4cf52  N03.json
db096a4a0358f9825e56a4f1cc3805deded6414f8268016b46c1477369646581  N04.json
2f14b8283cd5dbb6bc7b4f5e86c3822b168094161d49dc2348d6abc04f42320d  N05.json
5526d3e3a0751ede69155168de3c239562f8eb94919f7d6a5dc388f2424b6423  N06.json
488fefaf8c17cc86636f6a33d2328749ed9a26e16fa510322d9238afd4e6666a  N07.json
53b8c21e623719e5907bf19bb3b291b8ef78e339592563bab3845d56a479e0e2  N08.json
704f4e15ab351ed6fecc69ff708405d700f2fb82fa5473763c34cd63262f77ef  N09.json
199977870e4df6ff30f07fb6b261886da6680f205f12ea76c2c4e8e45955ad2b  N10.json
a11e2c8396a7f317b3ac3efb186ca18e9cac0f3b04803ca5a9c75c6b94db6557  N11.json
2e061957415f428c5c79a66b357255c5eb9d990f7cf32602271858c6be157dbe  N12.json
9ae889840e4aec2c4c7e4222ce2e7877190f4e573cfbf2dfeb9ed92ca80ee40e  N13.json
2b94aba1c27aaa0c81b7f2492d2760550b1b007e1e55b188dceaeecf257fd837  N14.json
550d5cefb4e93c9b6b5b1edc3429558fea33afa0d921586515df098257c025dd  N15.json
5d61c23696516f17af29efdec5771ca10f6fcb09c02c38f1685097eebb572592  N16.json
e0c33d625f815a59393d81caf8c30df1725c455d7987d65c09e35380f51e9d60  N17.json
b8a1059b49d4b054a0b99c904cbac49162ce86e858f58ce5e82bef1c6c792692  N18.json
9fec713ca12ea52fe361590f225e0308d56067795d19095f3bf3e928071dac35  N19.json
7557addd7f9783b1d46c977d3960c7a6d9148285eee6de3aad323ecf7d25899a  N20.json
2f1730a40d8f3eb22ca03e598d12e40ca014f8c9251fba01da9edbfc91940805  N21.json
b2cabb528101d70a985304167cb66ca1992ec0582337b4e058a5119ac54acb26  N22.json
768f5730d64fa83d27214126dc8251fff6e3b05b257f0fd40af43008d75eb061  N23.json
d75d558f0a93c72350a1e31cb92d26a2309ce938342c20e4bdbebc4a918074f5  N24.json
91e53b8df9473c74ec4d76b5162fe9a0c8e042ed8cabf72bb30478ba26d121d6  N25.json
2b17bfead9943b6a2a4731d54b54bb9b2ec9efcfec659110a5dbef8227febe52  N26.json
9e6b5470025df62280823066ee65a7942dab49e49d3b8764cbd4ee058df25056  N27.json
c15492f2168a5ed1657ddbd95160c1118aef694e1180cb557c60fbf1b7598b44  N28.json
acb630412d76d52db0153cf0a183525a5598ade218a8205305a70af03c2f2d38  N29.json
4c805ead8782bdddeb2a67a00a224147a0a954dc3d00ae73b008e6410fd49913  N30.json
26a691391fedfe4362b9c659d05deb6a1bb88ffc41dd350aa71faa6aa3d1bcd2  N31.json
193860a9edb9b272b798d1647f108553fe8e5ac3f7a08a0a3bc39ae9797e32db  N32.json
c48a74423680bb6a01ace05ecbd676c1c7d0927cb551292c8e39b7b6f6018698  N33.json
01ceab3e2a9f49dc28288c049d4596bca75d937942dfcc06a2a40cf74ec1b86c  N34.json
529421563966ea2cf151497f495a5a7097b12dd25052f2174ea81729a5b3b7f4  N35.json
edd168bdde0b4e003f75a523e0b45fdf8f4a0b15e8fb784e764fb7d57aea6754  N36.json
7ccccb7d6a96febe77102d832bdb9f81c0080e0e2f36e03d48ae08692212ec3d  N37.json
833c05c616e6543ad27d06f6c539c64cc952827571ffc8dc0aedb4044e07b79d  summary.json
e18391ab297a652e46971da053d46f610773920bfe26777fab4355a41e128ef1  summary.md
```

### run2

```
cb6d5a74a9fd5d23b22e8bb456a0328d3f8984fbcdd5389d6a87083e34c13a67  _meta/environment.json
b3d9ba7c899cfd112df2574c6a91458a70b724c5e4e50dfffd75574b2d1648e7  _meta/model-manifest.json
4aa147b5c54a0782466e360cc624c1c78b6fd900beb599ea583adfa0a2e70403  _meta/ollama-pull.log
460e309ae83ec81a5f4cb4a88e6ebf5ac5873796f0f9a036fd9dc5bd445d42a3  _meta/ollama-server.log
dca163f4bd8e4ad3f58f87d6cae77fef9d2d16fd8834450e4bfe2c08844b9e26  _meta/ollama-version.json
5e8cf0cade230c3c5673227781766a6e14c63c949f2b190f3efd81523efc7994  _meta/pip-freeze.txt
c67c1b29282772a507ba4dcf3aad29c206d67c77f0594d9052ae967a7e155f1a  _meta/pytest.log
500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41  _meta/registry-manifest.json
41a905e654947668dacdc46991d60a38263e8884ac37da3c04739482a962b8b6  _meta/run-status.json
8e47a696aa59c1cc41c4c548e5ed285b6c0cabcfd37f79a8d3f2bce33aa12f3e  _meta/run_eval.log
8bc16317b3c007372a438b947a45fcc41adc8c0e56afda22f110af51568acad2  N01.json
2d9140357bdb2678018a9fa6197cc0b1e863e5dfe1f2b7751891b5b68fd63440  N02.json
467ca8d23337d0c84e4f111484d4e259791eb2c6e4bebcc2a93a333055bf86a7  N03.json
82c8a0e21dce4c151104b999ddec80b341e6406926dbd8e19e6f35f25f8cba62  N04.json
cae277bd433e6f1b7af658ccecf52668f1697949f9c25ecb7781ac4bb5c48685  N05.json
49ac7567fbf9fa69793ed1e62dd189bb464f0290a192bbbcdb3d34d96f9e1938  N06.json
5bd332a531b2e1d530485c0ad9ea361236a57e887036ca9481d88eba04b275d1  N07.json
c33530f6678a045f7055a5e80a68db57e613bfffc97e9d05fac1d850578f4411  N08.json
544ff72c55c84c9afa5207beaa45d5a9483b900fa955cf2f9b076dd45f5b0715  N09.json
9c0c646eeea2f9f54368c127d8f3c9f45333983246b0aa6b823dcad49ab0bd3b  N10.json
655c9e29e0dfb065974eea8009a0f74ca4ee23695e8735b7d9607ae4827a5ff7  N11.json
0a2192e881c719cd643cf7d02f2568b4d6259368c1ac67e162faf4b297083f97  N12.json
15f13847c1981baebe11907951441cd3dd357e487e39c446ce06c6e07b848bf7  N13.json
1d0002182dfae712437f7c8eec9867018068e1d28e4315a69f016497710ee1bb  N14.json
7864a27a8f84278deedb5fb10f83bc243b7edcabd0db7ad143d4fa1ea4fb7d6d  N15.json
2f9800964aea4b9acdc729e2d81678d6fed536195f9057aadf4b3116a2b72534  N16.json
01bfd382faf7b3a53362034e7067ef05f14b6233b4053e69bceea8abe184d14e  N17.json
11ddb56e13fb89c71b0c60281dab0d5fc4fa98ed140f6b1b8221d0d7c904cd2f  N18.json
75bfd9319264fffe32582a2f389cf68d63217391ee806dd910b9c44c65c525a8  N19.json
0c1a64648d5bf7ef9b0a0efd05ab08a75b65ce643fbd2f60c794fe97cd87b07f  N20.json
e1c169c7bcc45877e4be5a224d868f02335d12024c29f06a386aa1e0a44cb8c8  N21.json
957101d5bcfd256607fcfbec68f64ef7888f24a8033054e775a9cbc0d9d79e6c  N22.json
0996d7d73f90ee96342f9ce5e5330eafb7b79f49f8e91b66a8f5cb26aea0e0ea  N23.json
dd62422789a93c9dbf1f2dc213c617181bd6c8e71a3f644a436f5c3d0762cf79  N24.json
5d18052ddc6e932d0994a59cf3306a0d9ad5fa800b28d2c53ba6dfd6e97c5e9c  N25.json
9845477a9994f7ae8df2e7c8a7ffd12847462351a08795f2b47dc0aa49b416de  N26.json
4877ac92de7de34c375b8f28375ea663666c99dfb7511c95f6af97127b8d52fd  N27.json
7b14213075c3aaec2ddf9231423b27c6bc81879e0bce06d3ca0ac42cc98969dc  N28.json
1a278c9f465ae016035b07696584de7b2d50f5b021a5d5e840edd3d4fc864fee  N29.json
7ec04fa172a6a3d44004eef9c600f06495c3e31045abfd8402a5204aa4ebe1b0  N30.json
03004ac8f37611c96e7e9c670f337fc32a8cbed3f88f74d20d691e8f43350f8a  N31.json
dd98fa35b175962a06c49a508023937f23748c8fbdfc99693d1b8085036eb8a0  N32.json
9032268bd7e3a87555f837c05fe52095e1ce57eab979e06760294f1ee40bd1ab  N33.json
d9a569326b5d1a13751f522e0f869008f78749c2ce8cfcc13b8f2636ca89c4ad  N34.json
8ee272b881b03d2deaaedd1fc19e4d7b10239214d9f947decc4d38624c1da394  N35.json
d5a037c1b2a749a786f1d2368ef3a85787ab9fedeea8563581395260359262ae  N36.json
29e6bfdf5750ede83e3ecd0862482669ca59bf444a79e0d16f4a6594e24e13db  N37.json
5a7995dc77768074fc75fe507317bacaaab15a6eb35a962ca92fe787528a69d2  summary.json
fd0783be15338bbced4b25d9f07c05ff0819b7fa324a20cba8f70713e3c11a32  summary.md
```

## How to reproduce

Dispatch `.github/workflows/heldout2-eval.yml` on `main` (handoff §8): mode `preflight`, then `fresh`
with `run1` and `run2`. Re-score a copy of a run folder under v2.1 with the scorer of `0b4030e` (handoff §8.5)
and compare runs with `evaluation/variability.py` (§8.6).
