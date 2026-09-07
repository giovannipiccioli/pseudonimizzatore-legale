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
Il ricorrente Ricorrente_1, C.F. CF_1, è rappresentato dall'avv. Difensore_1.
```

Il `rapporto` restituito spiega le operazioni effettuate:

```python
print(rapporto.mapping)
# {
#   'Mario Rossi': 'Ricorrente_1',
#   'RSSMRA80A01H501U': 'CF_1',
#   'Laura Bianchi': 'Difensore_1'
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
| codici fiscali, email/PEC, IBAN, telefoni, targhe, documenti di identità e date di nascita | sostituisci |
| indirizzi di residenza accompagnati da un contesto personale | sostituisci |
| segmenti esatti relativi a magistrati e pubblici ministeri | conserva |
| enti pubblici, istituzioni e nomi di luogo | conserva |
| numeri di procedimento ed ECLI | conserva |
| società private | conserva; sostituisci con `companies=True` |
| evidenze contrastanti di ruolo giudiziario e ruolo privato per la stessa identità | sostituisci e segnala per la revisione |

Le etichette sono stabili soltanto all'interno del singolo documento. In questo modo
non si crea un identificatore persistente che possa collegare la stessa persona tra
provvedimenti diversi.

## Configurare l'elaborazione

È possibile passare un oggetto `Config` oppure singole opzioni nominate:

```python
from pseudonimizzatore_legale import Config, anonymize

configurazione = Config(
    companies=True,
    keep_judges=True,
    keep_case_numbers=True,
    sanitize=True,
    verify=True,
)
risultato, rapporto = anonymize(testo, configurazione)

# Forma equivalente per una singola opzione:
risultato, rapporto = anonymize(testo, companies=True)
```

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

Il repository comprende 103 esempi annotati, relativi a materiale tributario, civile,
amministrativo, contabile, di Cassazione e dell'Unione europea. Il richiamo per entità
completa è una misura tutto-o-niente: se sopravvive anche un solo alias, l'intera
identità è considerata non rimossa.

| Configurazione | Entità complete | Richiamo sulle occorrenze | Limite inferiore di precisione | Valori protetti conservati | Documenti completi |
|---|---:|---:|---:|---:|---:|
| solo regex | 328/378 (86,8%) | 479/566 (84,6%) | 549/686 (80,0%) | 591/591 | 71/103 |
| + NER italiano XXL | 347/378 (91,8%) | 510/566 (90,1%) | 589/841 (70,0%) | 570/591 | 81/103 |
| + unione XXL e XLM-R | 349/378 (92,3%) | 513/566 (90,6%) | 591/870 (67,9%) | 570/591 | 83/103 |

Tutte le configurazioni rimuovono 107/107 identificatori strutturati annotati.
L'euristica di revisione intercetta tutti i 32 documenti con residui annotati, ma
segnala anche 67 documenti senza residui. È intenzionalmente una coda di revisione
orientata al richiamo, non un certificato di sicurezza.

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
modello italiano XXL è già presente nella cache di Hugging Face. La CI usa Python 3.10
e 3.12 ed esegue anche il playground.

## Architettura e struttura del progetto

In breve, la pipeline normalizza il testo, raccoglie le evidenze, risolve le identità
locali, applica le regole ai segmenti soltanto alla fine, produce il risultato in un
unico passaggio e lo analizza per individuare elementi da revisionare. Le motivazioni e
i punti di estensione sono descritti in [`ARCHITECTURE.md`](ARCHITECTURE.md).

```text
pseudonimizzatore_legale/ pacchetto della libreria
tests/                    test unitari e di integrazione
notebooks/                playground eseguibile
evaluation/corpus/        103 esempi con identità inventate
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
