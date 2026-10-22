# Third-party data notices

## First names registered in Italy

`pseudonimizzatore_legale/resources/first_names.json` is derived from
[italian_names_first_5000.xlsx](https://doi.org/10.6084/m9.figshare.3839580.v1),
published by Visigrad Data and in turn derived from ISTAT's *Conta nomi* data for
1999–2014. The source dataset is licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

The packaged resource contains only normalized single-token names with an aggregate
source count of at least 10. The original counts and year columns are not redistributed.

This notice does not imply endorsement by Visigrad Data or ISTAT.

## Italian comuni

`pseudonimizzatore_legale/resources/comuni.json` is derived from ISTAT's
[Elenco dei comuni italiani](https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.csv)
and [Elenco dei comuni soppressi](https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-soppressi.zip),
both as published in January 2024 and licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

The packaged resource contains only the case-folded names, Italian and other-language,
of current and suppressed comuni. Codes and the other columns are not redistributed.

This notice does not imply endorsement by ISTAT.

## Literary excerpts in the document benchmark

`evaluation/corpus_documents/narrativa/` holds four short excerpts of public-domain works
by Pirandello, Verga, Foscolo and Svevo, used only as evaluation data. The text comes from
the [it.wikisource.org](https://it.wikisource.org) transcriptions, available under
[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/); each excerpt's work and
page are in the `source` field of its `.gold.json`. The excerpts are not part of the
installed package.
