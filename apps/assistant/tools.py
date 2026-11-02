"""Outils de l'assistant IA — fonctions en LECTURE SEULE qui réutilisent le
code des rapports existants (mêmes chiffres garantis), plus la génération de
documents/images et la PROPOSITION d'actions (jamais exécutées ici).

Chaque outil a un « niveau » :
- STAFF  : tout le personnel connecté
- RESP   : responsables (superuser, ADMIN, DIRECTOR, MANAGER)
- DIR    : direction (superuser, ADMIN, DIRECTOR)
- ROOT   : superuser uniquement (propositions de modification)
"""
from datetime import date as date_cls
from decimal import Decimal

from django.utils import timezone

from apps.core.utils import BACKDATE_ROLES

# ---- Niveaux d'accès ----
STAFF, RESP, DIR, ROOT = 'STAFF', 'RESP', 'DIR', 'ROOT'


def niveau_user(user):
    if user.is_superuser:
        return ROOT
    if user.role in ('ADMIN', 'DIRECTOR'):
        return DIR
    if user.role in BACKDATE_ROLES:  # MANAGER
        return RESP
    return STAFF


_ORDRE = {STAFF: 0, RESP: 1, DIR: 2, ROOT: 3}


def autorise(user, niveau_requis):
    return _ORDRE[niveau_user(user)] >= _ORDRE[niveau_requis]


# ---- Schémas OpenAI/Groq ----

def _schema(name, description, properties=None, required=None):
    return {'type': 'function', 'function': {
        'name': name,
        'description': description,
        'parameters': {'type': 'object', 'properties': properties or {},
                       'required': required or []}}}


_DATE = {'type': 'string', 'description': "Date au format JJ/MM/AAAA (défaut : aujourd'hui)"}
_ANNEE = {'type': 'integer', 'description': "Année (défaut : année en cours)"}
_MOIS = {'type': 'integer', 'description': "Mois 1-12 (défaut : mois en cours)"}


def schemas_pour(user):
    """Liste des outils offerts au modèle selon le niveau de l'utilisateur."""
    tous = [
        (_schema('rapport_jour',
                 "Recettes, dépenses, parts prescripteurs versées et solde d'un jour. "
                 "Sans argument = aujourd'hui.",
                 {'date': _DATE}), STAFF),
        (_schema('recherche_patient',
                 "Recherche un patient par nom : fiche, entreprise, solde dû.",
                 {'nom': {'type': 'string', 'description': "Nom ou partie du nom"}},
                 ['nom']), STAFF),
        (_schema('generer_document',
                 "Génère un document Word (docx) ou PDF (lettre, rapport, compte rendu). "
                 "Le contenu accepte : '# Titre', '## Sous-titre', '- puce', **gras**.",
                 {'format': {'type': 'string', 'enum': ['docx', 'pdf']},
                  'titre': {'type': 'string'},
                  'contenu': {'type': 'string', 'description': "Texte complet du document"}},
                 ['format', 'titre', 'contenu']), STAFF),
        (_schema('generer_tableau',
                 "Génère un fichier Excel (xlsx) à partir de colonnes et lignes.",
                 {'titre': {'type': 'string'},
                  'colonnes': {'type': 'array', 'items': {'type': 'string'}},
                  'lignes': {'type': 'array', 'items': {'type': 'array'}}},
                 ['titre', 'colonnes', 'lignes']), STAFF),
        (_schema('generer_image',
                 "Génère une image à partir d'une description (affiche, illustration, logo…).",
                 {'description': {'type': 'string'}}, ['description']), STAFF),
        (_schema('rapport_mois',
                 "Recettes par module, dépenses, parts versées et solde d'un mois.",
                 {'annee': _ANNEE, 'mois': _MOIS}), RESP),
        (_schema('rapport_annee',
                 "Bilan mois par mois d'une année : perçus, dépenses, parts versées, solde.",
                 {'annee': _ANNEE}), RESP),
        (_schema('prescripteurs',
                 "Résumé des prescripteurs sur une période : actes labo/médecine/domicile, "
                 "parts totales, déjà versées et à verser.",
                 {'debut': _DATE, 'fin': _DATE}), RESP),
        (_schema('prescripteur_detail',
                 "Détail des actes d'un prescripteur (ex : 'Dr. Stany') : dates, patients, "
                 "montants, parts, statut de versement. Les lignes portent un #id utilisable "
                 "pour proposer un marquage « versée ».",
                 {'nom': {'type': 'string'}, 'debut': _DATE, 'fin': _DATE}, ['nom']), RESP),
        (_schema('liste_entreprises',
                 "Liste des entreprises partenaires des patients."), RESP),
        (_schema('rapport_entreprise',
                 "Rapport mensuel d'une entreprise partenaire (ex : LTJ) : séances kiné, "
                 "pharmacie & autres (consultations/évaluations incluses), coût, observation.",
                 {'nom': {'type': 'string'}, 'annee': _ANNEE, 'mois': _MOIS}, ['nom']), RESP),
        (_schema('dettes',
                 "Dettes en cours des patients (hors créances entreprises) : qui doit quoi."), RESP),
        (_schema('journal_activite',
                 "Journal d'audit d'un jour : qui a créé/modifié/exporté quoi et quand.",
                 {'date': _DATE}), DIR),
        (_schema('proposer_action',
                 "PROPOSE une modification (jamais exécutée directement — le superuser "
                 "confirme d'un clic). Actions : 'part_labo', 'part_medecine', "
                 "'part_domicile' avec parametres {'ids': [#id…]} ; 'depense' avec "
                 "{'label': str, 'montant': nombre, 'devise': 'USD'|'FC'}.",
                 {'action': {'type': 'string',
                             'enum': ['part_labo', 'part_medecine', 'part_domicile', 'depense']},
                  'parametres': {'type': 'object'},
                  'description': {'type': 'string',
                                  'description': "Résumé lisible de l'action pour la carte de confirmation"}},
                 ['action', 'parametres', 'description']), ROOT),
    ]
    return [s for s, niveau in tous if autorise(user, niveau)]


# ---- Helpers ----

def _parse_date(txt, defaut=None):
    if not txt:
        return defaut or timezone.localdate()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return timezone.datetime.strptime(str(txt).strip(), fmt).date()
        except ValueError:
            continue
    return defaut or timezone.localdate()


def _periode(args):
    today = timezone.localdate()
    d1 = _parse_date(args.get('debut'), today.replace(day=1))
    d2 = _parse_date(args.get('fin'), today)
    return d1, d2


def _mois_annee(args):
    today = timezone.localdate()
    try:
        mois = int(args.get('mois') or today.month)
        annee = int(args.get('annee') or today.year)
        if not 1 <= mois <= 12:
            raise ValueError
    except (ValueError, TypeError):
        return today.year, today.month
    return annee, mois


def _n(v):
    from apps.reports.services import _fmt_nombre
    return _fmt_nombre(v)


# ---- Exécution ----

def execute_tool(user, name, args):
    """Exécute un outil. Retourne (texte_pour_le_modele, artefact|None).
    artefact = {'kind': 'file', 'path', 'name', 'is_image'} ou
               {'kind': 'action', 'token', 'description'}"""
    from apps.reports import services as rs

    # ---------- Lecture : rapports ----------
    if name == 'rapport_jour':
        d = _parse_date(args.get('date'))
        return rs.whatsapp_daily(rs.daily_report(d)), None

    if name == 'rapport_mois':
        annee, mois = _mois_annee(args)
        return rs.whatsapp_monthly(rs.monthly_report(annee, mois)), None

    if name == 'rapport_annee':
        today = timezone.localdate()
        try:
            annee = int(args.get('annee') or today.year)
        except (ValueError, TypeError):
            annee = today.year
        return rs.whatsapp_annual(rs.annual_report(annee)), None

    if name == 'prescripteurs':
        d1, d2 = _periode(args)
        rows = rs.prescribers_summary(d1, d2)
        if not rows:
            return f"Aucun prescripteur entre le {d1:%d/%m/%Y} et le {d2:%d/%m/%Y}.", None
        lignes = [f"Prescripteurs du {d1:%d/%m/%Y} au {d2:%d/%m/%Y} :"]
        for e in rows:
            modules = []
            if e['labo_count']:
                modules.append(f"labo {e['labo_share_txt']}$ ({e['labo_count']} actes)")
            if e['med_count']:
                modules.append(f"médecine {e['med_share_txt']}$ ({e['med_count']})")
            if e['dom_count']:
                modules.append(f"domicile {e['dom_share_txt']}$ ({e['dom_count']})")
            lignes.append(f"- {e['name']} : total {_n(e['total_share'])}$ "
                          f"({', '.join(modules)}) — versée {_n(e['paid_share'])}$, "
                          f"à verser {_n(e['unpaid_share'])}$")
        return "\n".join(lignes), None

    if name == 'prescripteur_detail':
        d1, d2 = _periode(args)
        rep = rs.prescriber_report(args.get('nom', ''), d1, d2)
        if not rep['rows']:
            return f"Aucun acte trouvé pour « {args.get('nom')} » sur la période.", None
        lignes = [f"Actes de {rep['name']} ({rep['periode_txt']}) — "
                  f"facturé {rep['total_billed_txt']}$, part {rep['total_share_txt']}$ "
                  f"(versée {rep['total_paid_txt']}$, à verser {rep['total_unpaid_txt']}$) :"]
        for r in rep['rows']:
            lignes.append(f"- #{r['id']} [{r['activite']}] {r['date_txt']} — {r['patient']} — "
                          f"{r['detail']} — {r['montant_txt']}$ → part {r['part_txt']}$ "
                          f"({r['part_statut']})")
        return "\n".join(lignes), None

    if name == 'liste_entreprises':
        from apps.settings_app.models import Company
        entreprises = Company.objects.filter(is_active=True).order_by('name')
        if not entreprises:
            return "Aucune entreprise enregistrée.", None
        return "\n".join(
            f"- {c.name}{' (facturation à l’entreprise)' if c.facturation_entreprise else ''}"
            for c in entreprises), None

    if name == 'rapport_entreprise':
        from apps.settings_app.models import Company
        nom = (args.get('nom') or '').strip()
        company = Company.objects.filter(name__icontains=nom, is_active=True).first()
        if company is None:
            return f"Entreprise « {nom} » introuvable. Utilise liste_entreprises.", None
        annee, mois = _mois_annee(args)
        rep = rs.company_report(company, annee, mois)
        lignes = [f"Patients {company.name} — {rep['label']} :"]
        for r in rep['rows']:
            lignes.append(
                f"- {r['patient'].full_name} : pharmacie & autres {_n(r['pharmacie'])}$, "
                f"kiné {r['effectue']}/{r['prescrit']} séances ({r['cout_txt']}$), "
                f"obs : {r['observation'] or '—'}")
        lignes.append(f"TOTAL GÉNÉRAL : {_n(rep['total_general'])}$ — "
                      f"créance entreprise : {_n(rep['creance_usd'])}$")
        return "\n".join(lignes), None

    if name == 'dettes':
        from apps.finance.models import Invoice
        factures = [i for i in Invoice.objects
                    .exclude(status=Invoice.Status.CANCELLED)
                    .select_related('patient', 'patient__company')
                    .prefetch_related('payments') if i.balance_usd > 0]
        if not factures:
            return "Aucune dette en cours.", None
        patients, entreprises = [], []
        for i in factures:
            (entreprises if (i.patient and i.patient.company
                             and i.patient.company.facturation_entreprise)
             else patients).append(i)
        lignes = []
        if patients:
            total = sum(i.balance_usd for i in patients)
            lignes.append(f"Dettes patients ({len(patients)} facture(s), total {_n(total)}$) :")
            for i in sorted(patients, key=lambda x: -x.balance_usd)[:15]:
                lignes.append(f"- {i.patient.full_name} : {_n(i.balance_usd)}$ — {i.label}")
        if entreprises:
            total_e = sum(i.balance_usd for i in entreprises)
            lignes.append(f"Créances entreprises (réglées via le rapport entreprise) : "
                          f"{_n(total_e)}$")
        return "\n".join(lignes), None

    if name == 'recherche_patient':
        from apps.patients.models import Patient
        from django.db.models import Q
        nom = (args.get('nom') or '').strip()
        if len(nom) < 2:
            return "Donne au moins 2 lettres du nom.", None
        patients = Patient.objects.filter(
            Q(first_name__icontains=nom) | Q(last_name__icontains=nom)
            | Q(middle_name__icontains=nom), is_active=True)[:8]
        if not patients:
            return f"Aucun patient trouvé pour « {nom} ».", None
        lignes = []
        for p in patients:
            solde = sum(i.balance_usd for i in p.invoices
                        .exclude(status='CANCELLED').prefetch_related('payments'))
            ent = f" — entreprise : {p.company.name}" if p.company else ''
            lignes.append(f"- {p.full_name}{ent} — solde dû : {_n(solde)}$")
        return "\n".join(lignes), None

    if name == 'journal_activite':
        from apps.audit.models import AuditLog
        d = _parse_date(args.get('date'))
        events = AuditLog.objects.filter(created_at__date=d).select_related('user')[:30]
        if not events:
            return f"Aucun événement journalisé le {d:%d/%m/%Y}.", None
        lignes = [f"Journal du {d:%d/%m/%Y} ({len(events)} derniers événements) :"]
        for e in reversed(list(events)):
            qui = str(e.user) if e.user else 'système'
            lignes.append(f"- {e.created_at:%H:%M} — {qui} — "
                          f"{e.get_action_display()} [{e.module}] {e.object_repr}")
        return "\n".join(lignes), None

    # ---------- Génération de fichiers ----------
    if name == 'generer_document':
        from . import documents
        try:
            data, ext = documents.build_document(args.get('format'), args.get('titre', 'Document'),
                                                 args.get('contenu', ''))
        except ValueError as e:
            return str(e), None
        path = documents.save_generated(data, ext, args.get('titre'))
        return ("Document généré avec succès — dis à l'utilisateur qu'il peut le "
                "télécharger avec le bouton sous ta réponse.",
                {'kind': 'file', 'path': path, 'name': f"{args.get('titre', 'document')}.{ext}",
                 'is_image': False})

    if name == 'generer_tableau':
        from . import documents
        try:
            data, ext = documents.build_table(args.get('titre', 'Tableau'),
                                              [str(c) for c in args.get('colonnes', [])],
                                              args.get('lignes', []))
        except Exception:
            return "Tableau invalide (colonnes/lignes) — rien généré.", None
        path = documents.save_generated(data, ext, args.get('titre'))
        return ("Tableau Excel généré — dis à l'utilisateur qu'il peut le télécharger.",
                {'kind': 'file', 'path': path, 'name': f"{args.get('titre', 'tableau')}.{ext}",
                 'is_image': False})

    if name == 'generer_image':
        from . import documents, images
        data, erreur = images.generate_image(args.get('description', ''))
        if erreur:
            return erreur, None
        path = documents.save_generated(data, 'png', 'image')
        return ("Image générée — elle s'affiche directement dans la discussion.",
                {'kind': 'file', 'path': path, 'name': 'image.png', 'is_image': True})

    # ---------- Proposition d'action (superuser) ----------
    if name == 'proposer_action':
        if not user.is_superuser:
            return "[[HORS_PORTEE]] Seul le superuser peut demander des modifications.", None
        from . import actions as act
        action = args.get('action')
        if action not in act.ACTIONS:
            return "Action inconnue.", None
        token = act.build_token(action, args.get('parametres') or {})
        description = args.get('description') or act.describe(action, args.get('parametres') or {})
        return ("Action préparée — une carte de confirmation est affichée à l'utilisateur. "
                "Explique-lui ce qui sera fait et attends sa confirmation.",
                {'kind': 'action', 'token': token, 'description': description})

    return "Outil inconnu.", None
