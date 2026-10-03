# After submission

Two analyses I ran after submitting on 2 October 2026. They add to the technical report and change
none of its numbers; the submitted code is tag `v1.0`.

## The air-gapped model on the benchmark

The report says I had not scored the quantised model of the air-gapped setup. I have now run it on
the 60 decisions of the rewrite baseline (`--per-language 20`), with `make airgapped`'s setup:
Apertus v1.5 8B as GGUF Q4_K_M in llama.cpp `b11312`, on a Mac mini with Docker limited to 8 CPUs
and 12 GB, CPU only, on the sealed network, 2 requests in parallel.

| Same 60 decisions | Recall | Zero-leak | Over-redaction | Consistency | Model time per decision |
| --- | ---: | ---: | ---: | ---: | ---: |
| Velum, Apertus 70B, CSCS endpoint | 96.7% | 81.7% | 2.8% | 96.8% | 40 s |
| Velum, Apertus 8B, CSCS endpoint | 92.6% | 70.0% | 3.7% | 98.9% | 16 s |
| Velum, Apertus 8B Q4_K_M, llama.cpp on CPU, air-gapped | 86.0% | 63.3% | 0.3% | 98.8% | 559 s |

- **The quantised model loses 6.6 points of recall** against the same model on the CSCS endpoint,
  mostly on companies (77.4% against 98.1%) and persons (85.9% against 91.1%). It also removes
  fewer published names, so over-redaction drops.
- **It returns more names that are not in the text.** Velum rejected 212 mentions that do not
  occur verbatim, against 38 for the hosted 8B. Rejecting them keeps the output correct, and costs
  recall when the misspelt name was a real party.
- **Nothing outside the names changed** in any of the 60 outputs, as in every other Velum run: the
  diff guard does not depend on the model.
- **It is slow on CPU**: 4 hours 41 minutes for the 60 decisions, about 4.7 minutes per decision of
  wall time with 2 in parallel.

The comparison mixes two changes, the 4-bit quantisation and the serving stack (llama.cpp's chat
template and JSON-schema grammar), and each row is a single run. The 4-bit model on CPU works as an
offline fallback; the next things to measure are the 8-bit file (`docs/airgapped.md`) and the
unquantised model on a GPU, which I have not run.

Raw output and summary: `results/velum_Apertus-v1.5-8B-Q4_K_M-llamacpp_bger-2020_test.*`; the
hosted 8B scored on the same 60 is `results/velum_Apertus-v1.5-8B_bger-2020_test.per-language-20.summary.json`.

## Where the missed places come from

The 70B run removes 46.0% of the gold place mentions, the weakest kind in the report: 190 of 352
mentions leak. I labelled each of the 70 leaked place entities by hand from its context
([`analysis/place_misses_labels.tsv`](analysis/place_misses_labels.tsv), one row per entity with
its first leaked mention):

| Label | Entities | Mentions | What the BGer 2020 pack says |
| --- | ---: | ---: | --- |
| Residence or seat of a party ("domicilié à Versoix", "mit Sitz in Bülach") | 19 | 46 | pseudonymise (Art. 7 para. 1): a real miss |
| Authority or public body named after the place ("Comune di Losone" as respondent, "KESB Sarnen") | 14 | 60 | keep (Art. 4 para. 1 let. a) |
| Other place (where something happened, a workplace, a plot of land, an asylum seeker's route) | 37 | 84 | keep unless it is a party's residence or seat (Art. 4 para. 1 let. b, e) |

So 46 of the 190 leaked place mentions break the rules Velum applies. The other 144 are places the
federal rules keep but the court anonymised anyway, the same gap between rule and practice the
report describes for court-appointed experts. Eight of the 14 authorities come from cantonal courts
(Graubünden alone has four), which anonymise the municipality when it is a party; the federal pack
keeps it.

**A cue rule does not close the real misses.** I tested replacing every name that follows a
residence or seat cue ("Wohnsitz in", "mit Sitz in", "domicilié à", "con sede a" and similar), in
every occurrence, on top of Velum's edits. It recovers 27 of the 892 leaked gold mentions (recall
89.37% to 89.69%) and changes 486 letters and digits outside the gold, for instance every "Genève"
in a decision where a witness lives in Geneva. Most real misses are later mentions without a cue
("die Wohnung in Olten"), which only the model can tie to the party. I did not add the rule.

To reproduce: `python3 docs/analysis/place_misses.py` from `track_2b/` (no model call).
