# Anonymization API

Consider someone preparing a document for publication. A first pass suggests substitutions such as replacing a person's name with `Nominativo_1`. The reviewer reads the result, corrects a few substitutions, and marks a missed name. When a revised draft arrives, they want to reuse that work and check any newly introduced names or details.

Each call returns the pseudonymized text and a report. The report's `state` is the editable record of what to keep or replace. The reviewer can pass that record back with the revised source text.

## Principles

1. **Let the reviewer edit the engine's proposals directly.** Each entry records who or what was found, the decision, and any replacement. If nine of ten proposals are right, the reviewer edits the tenth and submits all ten. All ten then carry equal weight. A caller who already knows a participant's name can supply the same kind of entry before the first pass.
2. **Make the scope of a decision explicit.** A person who signs twice should normally get the same placeholder both times. Sometimes the same wording means two different things. The reviewer can set a rule for the whole document and make an exception for one passage.
3. **Preserve decisions when the wording changes.** Deleting “the applicant” may remove the clue that first identified a name. The saved entry lets the engine find that name again, while its detectors still look for new information. The current source and saved state are sufficient to resume in a new session.
4. **Put specialist knowledge in the engine.** A meeting note and a judgment both have people who may need pseudonyms. A legal engine can recognize the role `giudice` and apply a policy for judges. The application uses the same fields to review either document.

## From a meeting note to a reviewed state

```text
Marta Zappacosta presenta il progetto Aurora.
Firma: M. Zappacosta (studio@example.test).
Evento pubblico: Aurora.
Informazioni: eventi@example.test.
```

The caller starts with `output, report = anonymize(note)`. Looking at the proposals, the reviewer recognizes the abbreviated signature as Marta's, renames the private email's placeholder, and keeps the public enquiries address visible. They also mark *Aurora* as a confidential project name, with one exception where it names a public event.

Here are the three editable collections they submit. `people` holds identities, `data` holds other values, and `occurrences` holds decisions about individual passages. A caller can omit any empty collection.

```json
{
  "people": [
    {"id": "p1", "name": "Marta Zappacosta", "role": "persona",
     "aliases": ["M. Zappacosta"], "action": "redact", "placeholder": "Nominativo_1"}
  ],
  "data": [
    {"id": "d1", "value": "studio@example.test", "type": "email",
     "action": "redact", "placeholder": "Contatto_7"},
    {"id": "d2", "value": "eventi@example.test", "type": "email",
     "action": "keep", "placeholder": "Email_2"},
    {"id": "d3", "value": "Aurora", "type": "dato",
     "action": "redact", "placeholder": "Progetto_1"}
  ],
  "occurrences": [
    {"action": "keep", "anchor": {"quote": "Aurora", "prefix": "Evento pubblico: ", "suffix": "."}}
  ]
}
```

With this record as `reviewed_state`, the text returned by `anonymize(note, state=reviewed_state)` reads as follows. The public address retains its previously assigned `Email_2` in the state. Its `keep` action leaves the address visible.

```text
Nominativo_1 presenta il progetto Progetto_1.
Firma: Nominativo_1 (Contatto_7).
Evento pubblico: Aurora.
Informazioni: eventi@example.test.
```

### Decisions about an entity

| Field | Meaning |
| --- | --- |
| `name` and `role` in `people` | One person and their role in this document. The name is required. The engine fills a missing role from the text or uses its generic person role, e.g. `persona`. |
| `value` and `type` in `data` | One expression and its category. The value is required. An unclassified expression uses the generic data type, e.g. `dato`. This also allows arbitrary phrases to be kept or redacted. |
| `action` | `redact` substitutes a placeholder. `keep` leaves the matched text visible. When omitted, the engine applies the current policy. By default it redacts people and data. |
| `placeholder` | The literal replacement, independent of role or type. The engine allocates one when a redaction needs it. Renaming `Email_1` to `Contatto_7` leaves the type as `email`. |
| `aliases` | Optional alternative spellings for the same entity. Use these for document-wide equivalence. A surname shared by two people needs a decision at the relevant passage. |
| `id` | A unique reference within the document, supplied by the caller or assigned by the engine. It survives edits to a row, including renaming the placeholder. Occurrences can refer to it. |

### When the note changes

The editor moves the event to the first line and uses Marta's short name in a new sentence. The caller submits the reviewed state again.

```python
revised = "Evento pubblico: Aurora.\nM. Zappacosta aggiorna il progetto Aurora."
output, report = anonymize(revised, state=reviewed_state)
# Evento pubblico: Aurora.
# Nominativo_1 aggiorna il progetto Progetto_1.
```

An anchor stores the selected quote and nearby text from the normalized source. A UI can capture it from a selection. If a later edit moves the passage, a unique match still works. If the context changes or two passages match, the report lists the decision as unresolved for review.

An occurrence accepts `keep`, `redact`, or `dismiss`. A local redaction can use `entity_id` to share an existing entity's placeholder. Without a target it gets its own placeholder, saved on the occurrence, and creates no rule for other copies. A dismissal acknowledges a verification finding at that passage and leaves substitution decisions intact.

## Policy and replay

Reopening a first-pass review should reproduce exactly what the reviewer saw. With
the same source, engine and settings, this equality holds even after saving the
state as JSON and loading it in a fresh process.

```python
output, report = anonymize(source)
replayed, _ = anonymize(source, state=report.state)
assert replayed == output
```

A first pass records an optional `discovery_revision` alongside the three
collections. Keep it when saving the state. It identifies the normalized source
on which the proposals were found. For example, the engine might redact *Roma*
in a birthplace and leave *Tribunale di Roma* visible. On that source, reopening
the review or renaming the birthplace placeholder preserves both choices.

For a legal document the caller might know the participants before reading the text.

```python
state = {"people": [
    {"name": "Ada Malaspina", "role": "giudice"},
    {"name": "Marta Zappacosta", "role": "ricorrente", "placeholder": "Parte_7"}
]}
output, report = anonymize("Ada Malaspina ascolta Marta Zappacosta.",
                           config=Config(keep_roles=["giudice"]), state=state)
# Ada Malaspina ascolta Parte_7.

output, report = anonymize("Marta Zappacosta firma.", state=report.state)
# Parte_7 firma.
```

The returned rows contain concrete actions. Replaying this state keeps Ada and redacts Marta even if the new wording gives no clue to their roles. A reviewer can change an action directly. To apply a new role policy to selected rows, remove their `action` before replay. Removing a whole row allows fresh detection. Choosing `keep` records a lasting decision.

Three rules govern matching and substitution.

- Saved names, values, and aliases match complete expressions. A keep for `Aurora` cannot expose the longer detected email `aurora@example.test`. On an edited source, a saved value such as `Roma` can match a court heading as well as a birthplace. Use a passage exception to keep that heading visible. Ambiguous identities go to review.
- An anchored exception overrides the entity decision at that passage. If one mention stays visible and another is redacted, the report shows both outcomes. The entity still has one default action.
- An absent entity retains its row and any assigned placeholder. New entities receive unused placeholders. The report records matches and substitutions for the current revision.

The saved state contains original values and quoted passages. Treat it as source material when storing or sharing it.

## Restoring the originals

A pseudonymized document can go to a service that must not learn who is involved, such as a language model, and come back as new text that uses the tags. `restore` puts the originals back, using the state of the run that made the tags.

```python
state = {"people": [{"name": "Marta Zappacosta", "role": "ricorrente", "placeholder": "Parte_7"}]}
output, report = anonymize("Marta Zappacosta firma.", state=state)
# Parte_7 firma.
answer = "Parte_7 può impugnare l'avviso entro sessanta giorni."   # written with the tags
text, restoration = restore(answer, report.state)
# Marta Zappacosta può impugnare l'avviso entro sessanta giorni.
restoration.restored   # {'Parte_7': 1}
restoration.unknown    # []
```

- A person comes back as one spelling, whichever form the source used: the row's `name`, or its first alias that is not in capitals when the name came from a heading. A datum comes back as its `value`, and a passage redacted on its own as its quote.
- Tags are read as whole words, in any letter case and with the `\_` Markdown writers use for an underscore. A tag in capitals gets its original in capitals. Grammar written around a tag is left alone.
- A tag-shaped word the state does not know, such as an invented `Nominativo_9`, stays in place and is listed in `unknown`.

Restore each text with the state of the document whose tags it uses. Passing one document's `people` and `data` as the next document's state gives both documents the same tags, and the latest state then restores either. Whoever holds the state can restore every tag, so the rule above about storing it applies with full force.
