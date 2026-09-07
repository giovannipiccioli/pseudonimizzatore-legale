"""Invented identities used to build the test fixtures.

Every fixture in this library carries **invented** personal data, including the ones
built from real Cassazione decisions. Two reasons:

* a library whose purpose is keeping personal data out of downstream systems should not
  ship real parties' names in its own test corpus;
* injecting the names ourselves makes the gold standard exact — we know precisely which
  strings must disappear and which must survive, instead of guessing from the source.

None of these names, codici fiscali, IBANs or addresses belong to a real person. The
codici fiscali are format-valid (so the strict pattern fires) but the check character is
not computed, so they do not validate against the real algorithm.
"""

PEOPLE = [
    # (surname, first name)
    ("MALASPINA", "FERRUCCIO"),
    ("VIMERCATI", "ORTENSIA"),
    ("ROCCHETTI", "BALDASSARRE"),
    ("SANSEVERINO", "LUDOVICA"),
    ("FUMAGALLI", "ARISTIDE"),
    ("BONAVENTURA", "CELESTE"),
    ("TAGLIAFERRI", "NICODEMO"),
    ("MALINVERNI", "ISOTTA"),
    ("PICCININI", "GUALTIERO"),
    ("CAVALCANTI", "SERAFINA"),
    ("DELLA ROVERE", "AMEDEO"),
    ("LO STRANO", "PERPETUA"),
    ("DI BENEDETTO", "OSVALDO"),
    ("SCARAMUZZA", "ADELASIA"),
    ("VENTIMIGLIA", "TEODORO"),
    ("ZANGHERATTI", "MIRANDOLINA"),
]

COUNSEL = [
    ("TRENTACOSTE", "ERMENEGILDO"),
    ("BELLOCCIO", "ANASTASIA"),
    ("SPADACCINI", "GERVASIO"),
    ("QUARANTOTTO", "ILDEGARDA"),
    ("MONTELEONE", "ARCANGELO"),
    ("PIZZIGONI", "ROSALINDA"),
]

#: Judges — these must survive a run untouched, so fixtures assert on them.
JUDGES = [
    ("CORBELLINI", "AUGUSTO"),
    ("MASTROGIACOMO", "VITTORINA"),
    ("SBARAGLIA", "FEDERICO MARIA"),
    ("TREVISANATO", "ORNELLA"),
    ("RANIERI GRIMALDI", "SEVERINO"),
    ("PONTREMOLI", "CLOTILDE"),
]

COMPANIES = [
    "Vetreria Sanmartino S.r.l.",
    "Fonderie Corbelli S.p.A.",
    "Agriturismo Le Tre Querce S.a.s.",
    "Nautica Brancaleone S.n.c.",
    "Imballaggi Zeffirini S.r.l.",
]

#: Format-valid codici fiscali (6+2+month+day+letter+3+letter), invented.
CODICI_FISCALI = [
    "MLSFRC71D14F205X", "VMRRNS83M52L219K", "RCCBDS65B23H501Q",
    "SNSLDC90E48A662W", "FMGRTD58L07D612B", "BNVCST77T44G273N",
    "TGLNDM62P19C351M", "MLNSTT88H61E463P", "PCCGTR54R02B354T",
    "CVLSFN79A55I754D", "TRNRNG68C11L736V", "BLLNTS81S67F839G",
]

EMAILS = [
    "ferruccio.malaspina@studiomalaspina.it",
    "ortensia.vimercati@pec.avvocatiferrara.it",
    "b.rocchetti@legalmail.it",
    "studio.trentacoste@pec.ordineavvocatilucca.it",
    "anastasia.belloccio@postacert.legalitalia.it",
    "g.spadaccini@studiospadaccini.eu",
]

PEC = [
    "ermenegildo.trentacoste@pec.ordineavvocatipavia.it",
    "ludovica.sanseverino@legalmail.it",
]

PHONES = ["0532 774519", "081 5563127", "3357749218", "+39 011 4478230"]

IBANS = ["IT41J0300203280194752836471", "IT88K0538712900000004672913"]

ADDRESSES = [
    "Via Ippolito Nievo n. 47, 44121 Ferrara",
    "Piazza Guido Cavalcanti 3, 50122 Firenze",
    "Corso Ambrogio Traversari 118, 48121 Ravenna",
]

PARTITE_IVA = ["04738261095", "02956140374", "07412963058"]

TARGHE = ["FK472RD", "GT918PL"]


def person(i):
    """(SURNAME, NAME) pair, cycling through the bank."""
    return PEOPLE[i % len(PEOPLE)]


def counsel(i):
    return COUNSEL[i % len(COUNSEL)]


def judge(i):
    return JUDGES[i % len(JUDGES)]
