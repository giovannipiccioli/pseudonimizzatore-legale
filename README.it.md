# pseudonimizzatore_legale

**Italiano** · [English](README.md)

`pseudonimizzatore_legale` è una libreria Python locale per la pseudonimizzazione di
provvedimenti giudiziari italiani. Sostituisce le persone fisiche e i dati personali
strutturati con etichette leggibili e valide all'interno del singolo documento,
preservando magistrati, enti pubblici, luoghi e numeri di procedimento.

Il pacchetto si installa con il nome `pseudonimizzatore-legale`; negli import Python si
usa invece la forma con trattino basso `pseudonimizzatore_legale`.

```python
from pseudonimizzatore_legale import anonymize

testo = (
    "Il ricorrente Mario Rossi, C.F. RSSMRA80A01H501U, "
    "è rappresentato dall'avv. Laura Bianchi."
)

risultato, rapporto = anonymize(testo)
print(risultato)
```

```text
Il ricorrente Nominativo_1, C.F. CF_1, è rappresentato dall'avv. Nominativo_2.
```

Il `rapporto` restituito spiega le operazioni effettuate:

```python
print(rapporto.mapping)
# {
#   'Mario Rossi': 'Nominativo_1',
#   'RSSMRA80A01H501U': 'CF_1',
#   'Laura Bianchi': 'Nominativo_2'
# }

print(rapporto.status)
# passed_checks
```

> [!IMPORTANT]
> Questa è una pseudonimizzazione, non una garanzia di anonimato. `passed_checks`
> significa soltanto che le euristiche di controllo incluse nella libreria non hanno
> trovato residui. Prima della pubblicazione o divulgazione, il risultato deve essere
> revisionato.

## Installazione

È richiesto Python 3.10 o successivo. Da una copia locale del repository:

```bash
python -m pip install .
```

Per lo sviluppo:

```bash
python -m pip install -e ".[dev]"
```

Il motore di base funziona offline e ha una sola dipendenza a runtime. Il supporto NER
opzionale basato su transformer installa anche PyTorch e le librerie necessarie per i
tokenizer:

```bash
python -m pip install -e ".[ner]"
```

## Cosa viene rimosso

La configurazione predefinita è pensata per la pubblicazione di provvedimenti
giudiziari italiani:

| Evidenza | Comportamento predefinito |
|---|---|
| parti, difensori e persone fisiche private | sostituisci |
| codici fiscali, email/PEC, IBAN e numeri di conto, telefoni, numeri di carte di pagamento, targhe, documenti di identità e passaporti, numeri di iscrizione ad albi e registri, date di nascita | sostituisci |
| indirizzi di residenza, di domicilio eletto, di studio e di immobili introdotti dal loro contesto, e le righe di indirizzo di intestazioni, firme e destinatari | sostituisci |
| comuni di nascita e di residenza (`nato a Stia`), verificati sull'elenco ISTAT | sostituisci |
| segmenti esatti relativi a magistrati e pubblici ministeri | conserva |
| enti pubblici, istituzioni, le loro caselle istituzionali e i loro indirizzi, altri nomi di luogo | conserva |
| numeri di procedimento, ECLI e i nomi con cui si citano le cause europee (`Scoppola c. Italia`, `C-348/16, Sacko`) | conserva |
| società private | conserva; sostituisci le imprese probabilmente basate su nomi di persona con `companies="person_named"`, oppure tutte quelle rilevate con `companies=True` |
| evidenze contrastanti di ruolo giudiziario e ruolo privato per la stessa identità | sostituisci e segnala per la revisione |

Ogni persona diventa `Nominativo_N`. Con `roles=True` l'etichetta indica invece il ruolo
rilevato (`Ricorrente_1`, `Resistente_1`, `Difensore_1`); ciò che viene rimosso non cambia.

Le etichette sono stabili soltanto all'interno del singolo documento. In questo modo
non si crea un identificatore persistente che possa collegare la stessa persona tra
provvedimenti diversi.

## Configurare l'elaborazione

È possibile passare un oggetto `Config` oppure singole opzioni nominate:

```python
from pseudonimizzatore_legale import Config, anonymize

configurazione = Config(
    companies="person_named",
    roles=False,
    first_names=True,
    initials=False,
    keep_judges=True,
    keep_case_numbers=True,
    sanitize=True,
    verify=True,
)
risultato, rapporto = anonymize(testo, configurazione)

# Forma equivalente per una singola opzione:
risultato, rapporto = anonymize(testo, companies="person_named")
```

`first_names=True` attiva l'elenco incluso di nomi registrati in Italia. L'elenco è un
segnale debole, non un dizionario di sostituzione: riconosce un nome completo adiacente
come `Ferruccio Malaspina`, mai dentro il nome di una via, di un santo o di un comune. Un
nome proprio dell'elenco viene rimosso da solo soltanto come nome di una persona già
rilevata, oppure dopo un saluto o un rapporto di parentela (`Caro Paolo,`, `il figlio
minore Tommaso`). Impostare `False` per usare soltanto i rilevatori contestuali.
Questo aiuta anche con brevi stringhe non giuridiche, ma non costituisce una politica
separata per testi generali. La risorsa viene caricata al primo utilizzo e poi conservata
in memoria.

`initials=True` sostituisce le iniziali che alcune fonti scrivono al posto del nome
(`A.G. e S.I. hanno impugnato, nei confronti di S.T.`). Le iniziali sono pseudonime, non
anonime, e ricevono quindi un'etichetta come ogni altra parte. Le stesse lettere sono
anche il modo in cui il diritto italiano scrive le sue sigle (`P.Q.M.`, `D.P.R.`, `S.U.`):
la forma da sola non prova nulla. Le iniziali si prendono dopo gli indizi che fanno
riconoscere un nome (`proposto da`, `nei confronti di`, `avv.`, `nato a`…) e poi ovunque
ricorrano le stesse lettere. Restano intatte le sigle (`resources/sigle.json`), i
riferimenti (`art. 2697 C.C.`, `D.L. n. 78`), le iniziali di un giudice e le
organizzazioni (`R.B. s.p.a.`). `initials="all"` serve per una fonte che si sa scrivere le
parti con le iniziali: qualunque iniziale che nulla escluda è allora una persona, con o
senza indizio. È disattivata per impostazione predefinita perché cambia l'output, e non
va usata su testi che contengono soltanto sigle (sentenze tributarie, circolari). Restano
fuori di proposito le iniziali seguite da un cognome in chiaro (`G.M. Nonno`), quelle di
quattro lettere e le persone le cui iniziali coincidono con una sigla comune (`D.M.`).

`companies="person_named"` privilegia deliberatamente la precisione. Sostituisce le
società con un richiamo familiare esplicito (`F.lli`, `Fratelli` o `Eredi`) e i nomi
semplici formati da due parole con la forma di cognomi unite da `e` o `&`, come
`Mazzetti e Franchi s.r.l.`. Conserva nomi commerciali ambigui come `Labium spa` ed
`Etofi srl`, insieme a molte società che portano un solo cognome. È una piccola
euristica ortografica, non un registro dei cognomi né una promessa di copertura
completa. Usare `companies=True` quando la copertura conta più della precisione.

La libreria utilizza un'unica pipeline `legal`, indipendente dalla fonte del documento.
I profili storici `cassazione` e `generic` sono alias, non instradamenti specifici per
tipo di giudice o documento. `profile="query"` evita soltanto la scansione dei blocchi
estesi dedicati alle parti, ed è pensato per brevi stringhe interattive.

## Coerenza delle identità

Quando una persona viene individuata grazie a un contesto giuridico forte, la libreria
propaga le probabili varianti locali del nome. Un'intestazione con cognome e nome, una
forma ordinaria nel testo e il solo cognome distintivo possono quindi ricevere la
stessa etichetta:

```python
provvedimento = """sul ricorso proposto da
BENATTI ROSSELLA
-ricorrente-
Rossella Benatti insiste. La Benatti ricorre.
"""

risultato, rapporto = anonymize(provvedimento)
print(risultato)
print(rapporto.mapping)
```

La protezione dei ruoli giudiziari è locale al segmento. Un giudice chiamato
`ROSSI MARIO` non può proteggere globalmente una parte diversa chiamata `ROSSI LUCIA`.

## Comprendere il rapporto

I campi principali sono:

- `status`: `passed_checks`, `needs_review` oppure `not_run`;
- `mapping`: corrispondenza tra i valori sensibili originali e le etichette emesse;
- `decisions`: decisioni accettate di conservazione o sostituzione e relative evidenze;
- `residuals`: possibili dati personali ancora presenti nel risultato;
- `warnings`: evidenze contrastanti che richiedono una revisione;
- `replacement_spans`: posizioni, nel testo normalizzato, delle sostituzioni effettive;
- `risk`: punteggio di compatibilità per il triage; è preferibile usare `status` e i
  risultati concreti dei controlli.

`mapping` e i file laterali `*.map.json` prodotti dall'elaborazione in serie contengono
i valori sensibili originali. Devono essere trattati come dati sensibili. I file
laterali sono esclusi da `.gitignore`.

## Aggiungere il NER opzionale

Il NER è un ulteriore rilevatore di persone all'interno della stessa pipeline, non un
anonimizzatore separato:

```python
risultato, rapporto = anonymize(
    testo,
    ner="DeepMount00/Italian_NER_XXL_v2",
    ner_threshold=0.3,
    ner_device="cpu",
)
```

Per privilegiare il richiamo combinando due modelli:

```python
risultato, rapporto = anonymize(
    testo,
    ner=(
        "DeepMount00/Italian_NER_XXL_v2",
        "Davlan/xlm-roberta-base-ner-hrl",
    ),
    ner_threshold=0.3,
)
```

Al primo utilizzo Hugging Face scarica i pesi del modello, se non sono già presenti
nella cache. Il testo viene comunque elaborato localmente. Prima della distribuzione
in produzione è necessario verificare licenza e politica dei dati di ciascun modello.

## Elaborare una cartella

```python
from pseudonimizzatore_legale import anonymize_batch

riepilogo = anonymize_batch(
    "provvedimenti-in",
    "provvedimenti-out",
    workers=4,
    sidecar=True,
    resume=True,
)

for elemento in riepilogo["review_queue"]:
    print(elemento["dst"], elemento["status"], elemento["residuals"])
```

Le cartelle di origine e destinazione devono essere separate. Le scritture sono
atomiche, i collegamenti simbolici nella destinazione vengono rifiutati e un file con
UTF-8 non valido produce un errore limitato a quel file. La ripresa è facoltativa. Se
si usano i file laterali, prima di saltare un documento vengono verificati gli hash di
origine e risultato, la configurazione, lo schema del rapporto e la versione del
motore.

Per elaborazioni NER in serie, conviene iniziare con `ner_device="cpu"`: più processi
che competono per lo stesso acceleratore possono essere più lenti della CPU. Per
riprese riproducibili è consigliato usare uno snapshot locale e immutabile del modello.

## Playground

[`notebooks/01_playground.ipynb`](notebooks/01_playground.ipynb) è una guida eseguibile
e commentata all'API essenziale, alla configurazione, alla coerenza delle identità, allo
stato di revisione, al NER opzionale e all'elaborazione di file. Per utilizzarla:

```bash
python -m pip install -e ".[notebooks]"
jupyter lab notebooks/01_playground.ipynb
```

Tutte le identità presenti nel notebook e nel corpus di valutazione incluso nel
repository sono inventate.

## Prestazioni misurate

Il repository comprende 124 esempi annotati, relativi a materiale tributario, civile,
amministrativo (Consiglio di Stato e TAR), contabile, di Cassazione e dell'Unione
europea. Il richiamo per entità completa è una misura tutto-o-niente: se sopravvive
anche un solo alias, l'intera identità è considerata non rimossa.

| Configurazione | Entità complete | Richiamo sulle occorrenze | Limite inferiore di precisione | Valori protetti conservati | Documenti completi |
|---|---:|---:|---:|---:|---:|
| base contestuale (`first_names=False`) | 448/488 (91,8%) | 705/768 (91,8%) | 782/942 (83,0%) | 722/726 | 97/124 |
| predefinita (+ elenco dei nomi) | 472/488 (96,7%) | 746/768 (97,1%) | 817/989 (82,6%) | 718/726 | 111/124 |
| + NER italiano XXL, elenco disattivato | 475/488 (97,3%) | 748/768 (97,4%) | 836/1126 (74,2%) | 698/726 | 111/124 |
| predefinita + NER italiano XXL | 477/488 (97,7%) | 751/768 (97,8%) | 838/1130 (74,2%) | 696/726 | 113/124 |

Tutte e quattro le configurazioni rimuovono 115/115 identificatori strutturati annotati.
L'elenco porta il richiamo dei nomi completi dall'89,3% al 95,7% senza dipendenze da
modelli. L'euristica di revisione intercetta ogni documento con residui annotati, ma
rimane intenzionalmente rumorosa. Non è un certificato di sicurezza.

Per definizioni, risultati per fonte, compromessi e comandi di riproduzione, vedere
[`evaluation/RECALL_BENCHMARK.md`](evaluation/RECALL_BENCHMARK.md).

## Test

La suite di test deterministici e gli esempi di valutazione pseudonimizzati sono
inclusi nel repository:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python evaluation/build_corpus/check_fixtures.py
python evaluation/score_corpus.py
```

I test facoltativi con modelli reali vengono eseguiti automaticamente quando il
modello italiano XXL è già presente nella cache di Hugging Face. Non c'è una CI: cosa
eseguire prima di una modifica, playground compreso, è in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Architettura e struttura del progetto

In breve, la pipeline normalizza il testo, raccoglie le evidenze, risolve le identità
locali, applica le regole ai segmenti soltanto alla fine, produce il risultato in un
unico passaggio e lo analizza per individuare elementi da revisionare. Le motivazioni e
i punti di estensione sono descritti in [`ARCHITECTURE.md`](ARCHITECTURE.md).

```text
pseudonimizzatore_legale/ pacchetto della libreria
tests/                    test unitari e di integrazione
notebooks/                playground eseguibile
evaluation/corpus/        124 esempi con identità inventate
evaluation/               metriche e strumenti per costruire il corpus
```

## Origine e ringraziamenti

Questo progetto nasce da [**Anonimator**](https://github.com/avvocati-e-mac/anonimator),
lo strumento offline per la pseudonimizzazione di documenti legali creato da
**Filippo Strozzi**. In particolare, Anonimator ha fornito le idee e i pattern iniziali
per i ruoli giuridici italiani, gli identificatori strutturati, l'elaborazione locale e
il rilevamento ibrido tramite espressioni regolari e NER.

Questo repository rielabora quel punto di partenza in una libreria Python indipendente
dal tipo di documento e guidata dai test, con applicazione tardiva delle regole,
propagazione locale delle identità, controllo dei residui, elaborazione sicura in serie
e valutazione per entità. Grazie a Filippo Strozzi per aver reso disponibile il progetto
originale.

## Contributi, sicurezza e licenza

Prima di proporre una modifica, leggere [`CONTRIBUTING.md`](CONTRIBUTING.md). Non
inserire mai dati personali reali in una segnalazione, un test o un esempio. Per
segnalazioni relative a sicurezza e riservatezza, seguire
[`SECURITY.md`](SECURITY.md).

Distribuito con licenza MIT. Vedere [`LICENSE`](LICENSE). La licenza conserva
l'indicazione di copyright sia per le parti derivate da Anonimator sia per questa
implementazione Python.
La risorsa dei nomi inclusa ha un'attribuzione separata con licenza CC BY 4.0; vedere
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
