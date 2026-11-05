"""Whole decisions, each in the shape of a source, with `initials` off, prudent and everywhere.

The configuration is the one the Cassazione consolidation notebook runs: the prudent
reading for every source, and the everywhere reading for the one that writes its parties as
initials (ilforo). Each expectation is the input with exactly the listed replacements, so
the test says what changed and, by omission, everything that did not: the judges, the case
numbers, the sigle and the references.

All names are invented, in the shape of the decisions they stand for.
"""
import dataclasses

import pytest

from pseudonimizzatore_legale import Config, anonymize

NOTEBOOK = Config(profile="legal", companies="person_named", keep_judges=True,
                  keep_case_numbers=True, sanitize=True, verify=True, ner=None, roles=True)
OFF = NOTEBOOK
PRUDENT = dataclasses.replace(NOTEBOOK, initials=True)
EVERYWHERE = dataclasses.replace(NOTEBOOK, initials="all")


def replaced(text, tags):
    for old, new in tags.items():
        assert old in text, old
        text = text.replace(old, new)
    return text


def gap(reason):
    return pytest.mark.xfail(strict=True, reason=reason)


#: A Cassazione civil ordinanza as ilforo prints it: every private name is its initials.
ILFORO_CIVIL = """\
REPUBBLICA ITALIANA
IN NOME DEL POPOLO ITALIANO
LA CORTE SUPREMA DI CASSAZIONE
SEZIONE LAVORO

Composta dagli Ill.mi Sigg.ri Magistrati:
Dott. Adelmo Foscarini - Presidente -
Dott. Ines Caruso - Consigliere -
Dott. Ottavio Benedetti - Rel. Consigliere -
ha pronunciato la seguente

ORDINANZA
sul ricorso 4821-2020 proposto da:
A.G., elettivamente domiciliato in ROMA, VIA DEI GRACCHI 12, presso lo studio dell'avvocato B.N., che lo rappresenta e difende;
- ricorrente -
contro
S.T., domiciliata in ROMA, rappresentata e difesa dall'avvocato L.S.;
- controricorrente -
avverso la sentenza n. 1054/2019 della CORTE D'APPELLO di ROMA, depositata il 12/03/2019 R.G.N. 3321/2016;
udita la relazione della causa svolta nella camera di consiglio del 15/02/2023 dal Consigliere Dott. Ottavio Benedetti.

FATTI DI CAUSA
1. A.G. conveniva in giudizio S.T., sua datrice di lavoro, chiedendo l'accertamento della natura subordinata del rapporto. Il Tribunale rigettava la domanda; la Corte d'appello, con la sentenza indicata in epigrafe, confermava la decisione, ritenendo che A.G. non avesse provato l'eterodirezione.
2. Per la cassazione propone ricorso A.G. con due motivi, ai sensi dell'art. 360, n. 3, c.p.c. e dell'art. 2094 C.C. S.T. resiste con controricorso. Il P.G. ha concluso per il rigetto.

RAGIONI DELLA DECISIONE
Il ricorso è infondato (Cass. S.U. n. 2970 del 2011; D.Lgs. n. 81 del 2015). P.Q.M. rigetta il ricorso e condanna A.G. alle spese.
"""

ILFORO_CIVIL_INITIALS = {"A.G.": "Ricorrente_1", "B.N.": "Difensore_1", "S.T.": "Resistente_1",
                         "L.S.": "Difensore_2"}
ILFORO_CIVIL_OTHER = {"VIA DEI GRACCHI 12": "Indirizzo_1"}

#: A Cassazione penal sentenza from the same source.
ILFORO_PENAL = """\
SENTENZA
sul ricorso proposto da:
C.L. nato a TORINO il 12/03/1970
avverso la sentenza del 14/11/2022 della CORTE DI APPELLO DI ROMA
visti gli atti, il provvedimento impugnato e il ricorso;
udita la relazione svolta dal Consigliere Dott. Eugenio Massa;
udito il Pubblico Ministero, in persona del Sostituto Procuratore generale Dott. Lia Sorrentino, che ha concluso per il rigetto;
udito il difensore, avv. M.F. del foro di ROMA.

RITENUTO IN FATTO
1. Con la sentenza impugnata la Corte di appello di Roma ha confermato la condanna di C.L. per il reato di cui all'art. 316-bis c.p., pronunciata dal Tribunale. La parte civile N.F. ha chiesto la conferma delle statuizioni civili.
2. Il difensore di C.L. deduce violazione di legge. Il teste T.R. ha riferito che D.P.R. 633/72 non era stato richiamato.
CONSIDERATO IN DIRITTO
Il ricorso è inammissibile. P.Q.M. dichiara inammissibile il ricorso e condanna C.L. al pagamento delle spese processuali.
"""

ILFORO_PENAL_INITIALS = {"C.L.": "Ricorrente_1", "M.F.": "Difensore_1", "N.F.": "Nominativo_1",
                         "T.R.": "Nominativo_2"}
ILFORO_PENAL_OTHER = {"TORINO": "Luogo_1", "12/03/1970": "Data_nascita_1"}

#: A tax decision: sigle and references only, no person written as initials.
TAX = """\
Svolgimento del processo
La società contribuente impugnava l'avviso di accertamento per I.R.P.E.F., I.R.A.P. e I.V.A. relativo al 2012, emesso ai sensi del D.P.R. 600/73 e del D.P.R. 633/72. La C.T.P. accoglieva il ricorso; l'Agenzia delle Entrate (A.E.) proponeva appello alla C.T.R., che lo rigettava. Il C.T.U. nominato ha accertato maggiori ricavi. Il P.M. non è intervenuto.
Ricorrono ai sensi dell'art. 21 D.Lgs. n. 546/1992 (C.F.: non indicato). Cass., S.U., n. 26635 del 2009. Il comune ha disposto l'art. 7 L.R. n. 12/2005 e il P.R.G.
"""

#: A civil merito judgment whose parties are already placeholders.
MERITO = """\
TRIBUNALE DI MILANO
Nella causa civile iscritta al n. 1234/2020 R.G. promossa da:
Parte_1 (C.F. M___), con il patrocinio dell'avv. M___
ATTRICE
contro
Controparte_1 (P.IVA M___), con il patrocinio dell'avv. M___
CONVENUTA
Il G.I., dott. Carla Neri, letti gli atti; visto l'art. 183 c.p.c.; P.Q.M. rigetta la domanda.
"""

#: A Corte costituzionale ordinanza: a party written as initials, a role word after it.
CORTE_COST = """\
ORDINANZA
nel giudizio di legittimità costituzionale dell'art. 5, comma 2, del D.L. 31 maggio 2010, n. 78, promosso dal Tribunale ordinario di Roma, sezione lavoro, nel procedimento vertente tra A.B. e l'I.N.P.S., con ordinanza del 12 aprile 2021, iscritta al n. 87 del registro ordinanze 2021.
Ritenuto che, con l'ordinanza indicata in epigrafe, il Tribunale ha sollevato questione di legittimità costituzionale dell'art. 5 del D.L. n. 78 del 2010, in riferimento agli artt. 3 e 38 della Costituzione;
che nel giudizio principale A.B., ricorrente, ha dedotto di avere diritto alla prestazione; che l'I.N.P.S., convenuto, si è costituito.
"""


def test_ilforo_civil_without_the_option_keeps_the_initials():
    assert anonymize(ILFORO_CIVIL, OFF)[0] == replaced(ILFORO_CIVIL, ILFORO_CIVIL_OTHER)


@pytest.mark.parametrize("config", [PRUDENT, EVERYWHERE], ids=["prudent", "everywhere"])
def test_ilforo_civil(config):
    assert anonymize(ILFORO_CIVIL, config)[0] == replaced(
        ILFORO_CIVIL, {**ILFORO_CIVIL_INITIALS, **ILFORO_CIVIL_OTHER})


def test_ilforo_penal_without_the_option_keeps_the_initials():
    assert anonymize(ILFORO_PENAL, OFF)[0] == replaced(ILFORO_PENAL, ILFORO_PENAL_OTHER)


@pytest.mark.parametrize("config", [PRUDENT, EVERYWHERE], ids=["prudent", "everywhere"])
def test_ilforo_penal(config):
    assert anonymize(ILFORO_PENAL, config)[0] == replaced(
        ILFORO_PENAL, {**ILFORO_PENAL_INITIALS, **ILFORO_PENAL_OTHER})


@pytest.mark.parametrize("config", [PRUDENT, EVERYWHERE], ids=["prudent", "everywhere"])
def test_a_tax_decision_full_of_sigle_is_not_touched(config):
    assert anonymize(TAX, config)[0] == anonymize(TAX, OFF)[0] == TAX


@pytest.mark.parametrize("config", [PRUDENT, EVERYWHERE], ids=["prudent", "everywhere"])
def test_a_merito_judgment_with_placeholders_is_not_touched(config):
    assert anonymize(MERITO, config)[0] == anonymize(MERITO, OFF)[0]


def test_corte_costituzionale_prudent_reading_leaves_the_sigle():
    assert anonymize(CORTE_COST, PRUDENT)[0] == anonymize(CORTE_COST, OFF)[0]


def test_corte_costituzionale_everywhere_reading_takes_the_party_and_not_the_ente():
    assert anonymize(CORTE_COST, EVERYWHERE)[0] == replaced(
        anonymize(CORTE_COST, OFF)[0], {"A.B.": "Nominativo_1"})


@gap("a role word after the initials ('A.B., ricorrente') is not a cue")
def test_corte_costituzionale_prudent_reading_takes_a_party_named_before_its_role():
    assert "A.B." not in anonymize(CORTE_COST, PRUDENT)[0]
