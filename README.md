# 🏥 Centre Médical — Plateforme de Gestion

> **Application web de gestion médicale, financière et administrative avec messagerie interne.**

## 👨🏽‍💻 Auteur

**Ir. Rossy Wanose**  
*Future Ingénieur Logiciel*

---

## 📌 Présentation

Ce projet consiste à développer une application web professionnelle destinée à la gestion globale d'un centre médical.

L'application centralisera notamment :

- la gestion des patients ;
- les activités quotidiennes du centre ;
- les recettes, dépenses, dettes et créances ;
- la pharmacie et la gestion des stocks ;
- le laboratoire ;
- les soins à domicile ;
- les rendez-vous et le calendrier ;
- les rapports journaliers, mensuels et annuels ;
- la configuration générale du centre ;
- les utilisateurs, rôles et permissions ;
- une messagerie interne inspirée des principales fonctionnalités d'une application comme WhatsApp.

L'objectif est de disposer d'une **plateforme unique, moderne, sécurisée et évolutive** permettant au personnel autorisé de gérer les opérations du centre depuis une seule interface.

---

# 🎯 Objectifs du projet

## Objectif général

Concevoir et développer une plateforme web permettant de gérer efficacement les activités médicales, administratives et financières d'un centre médical.

## Objectifs spécifiques

- Centraliser les informations des patients.
- Faciliter l'enregistrement et la recherche rapide d'un patient.
- Suivre les séances prescrites, effectuées et restantes.
- Gérer les paiements en **USD ($)** et en **Franc congolais (FC)**.
- Conserver le taux de change utilisé lors de chaque opération financière.
- Gérer les recettes et les dépenses.
- Gérer les produits et les stocks de pharmacie.
- Suivre les activités du laboratoire.
- Gérer les soins à domicile.
- Gérer les rendez-vous.
- Produire des rapports professionnels.
- Assurer la traçabilité des actions effectuées par les utilisateurs.
- Fournir une messagerie interne avec communication en temps réel.
- Garantir un contrôle d'accès basé sur les rôles et permissions.

---

# 🧱 Architecture fonctionnelle

```text
CENTRE MÉDICAL
│
├── 🏠 Tableau de bord
├── 🏥 Centre
│   ├── Activités du jour
│   ├── Patients
│   ├── Séances
│   ├── Recettes
│   ├── Dépenses
│   ├── Créances
│   └── Dettes
├── 💊 Pharmacie
├── 🧪 Laboratoire
├── 🏠 Soins à domicile
├── 📅 Calendrier
├── 📊 Rapports
├── 💬 Messagerie
├── ⚙️ Configuration
├── 👤 Profil
├── 🔐 Authentification
└── 📝 Journal d'activité
```

---

# 🛠️ Technologies

## Frontend

- **HTML5**
- **Tailwind CSS**
- **JavaScript**

## Backend

- **Python**
- **Django**
- **Django REST Framework**

## Base de données

- **PostgreSQL**

## Temps réel

- **Django Channels**
- **WebSocket**

## Génération de documents

- PDF
- Excel
- Word

---

# 🎨 Interface utilisateur

L'interface devra être moderne, professionnelle, responsive et adaptée aux ordinateurs, tablettes et mobiles.

La couleur principale sera basée sur le **vert et le blanc**, conformément à l'identité souhaitée pour un centre médical.

L'application prendra en charge :

- le mode clair ;
- le mode sombre ;
- la détection du thème du système ;
- la personnalisation de certaines couleurs depuis les paramètres.

---

# 🏥 Gestion des patients

Chaque patient pourra être recherché rapidement dans la base de données.

Si le patient existe, ses informations sont automatiquement récupérées, ses séances sont suivies et ses paiements sont consultables.

Si le patient n'existe pas, une fenêtre de création permettra de l'enregistrer.

## Informations principales

- Nom
- Post-nom
- Prénom
- Sexe
- Lieu de naissance
- Date de naissance
- Entreprise
- Téléphone
- Nombre de séances prescrites
- Nombre de séances effectuées
- Nombre de séances restantes
- Jour de séance : pairs, impairs ou tous
- Montant à payer
- Montant payé
- Montant restant

---

# 💰 Gestion financière

Le système devra gérer les recettes, dépenses, paiements des patients, dettes, créances et soldes.

## Devises

Deux devises sont prévues : **USD ($)** et **Franc congolais (FC)**.

Un taux de change configurable sera utilisé pour les conversions.

Exemple :

```text
1 USD = 2 250 FC
10 USD = 22 500 FC
```

Chaque opération financière devra conserver le **taux réellement utilisé au moment de la transaction**, afin que les anciennes transactions restent historiquement cohérentes.

---

# 💊 Pharmacie

Le module pharmacie permettra de créer et modifier les produits, gérer les quantités, enregistrer les ventes, diminuer automatiquement le stock, contrôler les stocks disponibles et suivre les dates d'expiration.

## Produit

- Nom
- Prix unitaire
- Quantité initiale
- Quantité restante
- Date d'expiration
- Observation

---

# 🧪 Laboratoire

Le module laboratoire suivra les examens effectués : date, patient, examen, prescripteur, montant facturé, part du prescripteur, part de l'équipe du laboratoire, part du centre et observation.

### Répartition par défaut

```text
20 % → Prescripteur

80 % restants :
├── 60 % → Équipe laboratoire
└── 40 % → Centre
```

Les pourcentages seront configurables.

---

# 🏠 Soins à domicile

Le module permettra de gérer le patient, les prestations/séances, le médecin traitant, les séances prescrites/effectuées/restantes, la facturation, les paiements, le montant restant et la répartition des revenus.

---

# 📅 Calendrier et rendez-vous

Un calendrier professionnel permettra de planifier les rendez-vous sur plusieurs années.

Un rendez-vous pourra contenir :

- patient ;
- motif ;
- médecin ;
- date ;
- rappel ;
- alarme ;
- informations complémentaires.

---

# 📊 Rapports

Le système produira des rapports journaliers, mensuels et annuels.

Formats prévus :

- PDF ;
- Excel ;
- Word ;
- message structuré pour le rapport journalier.

Le rapport annuel intégrera des graphiques professionnels.

---

# 💬 Messagerie interne

La plateforme intégrera une messagerie interne avec :

- conversations individuelles ;
- groupes ;
- messages texte ;
- emojis ;
- messages vocaux ;
- images ;
- vidéos ;
- fichiers et documents ;
- recherche dans les conversations ;
- mise en forme du texte ;
- messages éphémères ;
- conservation permanente selon la configuration.

La messagerie sera conçue comme un **module indépendant**.

---

# 🔐 Authentification et sécurité

L'application devra disposer d'une authentification sécurisée, d'une gestion des sessions, de rôles et de permissions.

La création de compte sera réservée aux personnes autorisées. Le cahier des charges prévoit des codes de sécurité ; la solution finale devra privilégier une gestion sécurisée côté serveur plutôt qu'un simple fichier exposé.

---

# 👥 Rôles et permissions

Exemples de rôles :

```text
Administrateur
Directeur
Assistant gestionnaire
Médecin
Laborantin
Pharmacien
Kinésithérapeute
Autre personnel
```

Permissions possibles :

```text
CONSULTER
CRÉER
MODIFIER
SUPPRIMER
EXPORTER
ADMINISTRER
```

---

# 📝 Journal d'activité

Les opérations importantes devront être traçables : utilisateur, action, module, date/heure, élément concerné et, lorsque nécessaire, ancienne et nouvelle valeur.

---

# ⚙️ Configuration générale

La configuration permettra notamment de gérer :

- personnel ;
- entreprises ;
- taux de change ;
- examens de laboratoire ;
- répartition laboratoire ;
- répartition soins à domicile ;
- paramètres généraux ;
- identité visuelle ;
- couleurs de l'application.

---

# 📱 Tableau de bord

Le tableau de bord donnera une vue synthétique de l'activité : patients, recettes, dépenses, créances, dettes, pharmacie, laboratoire, soins à domicile, rendez-vous et dernières actions.

---

# 🗂️ Structure technique prévue

```text
medical_center/
│
├── config/
├── apps/
│   ├── accounts/
│   ├── patients/
│   ├── centre/
│   ├── finance/
│   ├── pharmacy/
│   ├── laboratory/
│   ├── home_care/
│   ├── appointments/
│   ├── reports/
│   ├── messaging/
│   ├── settings/
│   └── audit/
├── templates/
├── static/
│   ├── css/
│   ├── js/
│   └── images/
├── media/
├── manage.py
├── requirements.txt
└── README.md
```

---

# 🚀 Méthodologie de développement

## Phase 1 — Fondations

- Création du projet Django
- Configuration PostgreSQL
- Configuration Tailwind CSS
- Structure des applications
- Variables d'environnement
- Configuration de sécurité

## Phase 2 — Authentification

- Utilisateurs
- Connexion/déconnexion
- Rôles
- Permissions
- Profil
- Journal d'activité

## Phase 3 — Patients

- Modèle Patient
- Création
- Recherche
- Modification
- Consultation
- Historique
- Séances

## Phase 4 — Finance

- Recettes
- Paiements
- Dépenses
- Dettes
- Créances
- Multi-devise
- Taux de change
- Historique des transactions

## Phase 5 — Services

- Pharmacie
- Laboratoire
- Soins à domicile

## Phase 6 — Calendrier

- Rendez-vous
- Rappels
- Notifications

## Phase 7 — Rapports

- Journalier
- Mensuel
- Annuel
- PDF
- Excel
- Word
- Graphiques

## Phase 8 — Messagerie

- Conversations
- WebSocket
- Messages
- Groupes
- Fichiers
- Médias
- Messages vocaux

## Phase 9 — Finalisation

- Tests
- Sécurité
- Optimisation
- Responsive design
- Documentation
- Déploiement

---

# 🧪 Tests

Chaque module devra être testé avant son intégration complète : modèles, formulaires, vues, API, permissions, calculs financiers, conversions, stocks, rapports et messagerie temps réel.

---

# 🔒 Principes de sécurité

- mots de passe correctement hachés ;
- protection CSRF ;
- validation des données côté serveur ;
- contrôle des permissions côté backend ;
- protection des fichiers uploadés ;
- journalisation des opérations importantes ;
- variables sensibles dans l'environnement ;
- aucune clé secrète directement dans le code source ;
- sauvegardes régulières de la base de données.

---

# 📋 État du projet

| Module | État |
|---|---|
| Cahier des charges | 🟢 Défini |
| Architecture | 🟡 En conception |
| Base de données | 🔴 À concevoir |
| Authentification | 🔴 À développer |
| Patients | 🔴 À développer |
| Finance | 🔴 À développer |
| Pharmacie | 🔴 À développer |
| Laboratoire | 🔴 À développer |
| Soins à domicile | 🔴 À développer |
| Calendrier | 🔴 À développer |
| Rapports | 🔴 À développer |
| Messagerie | 🔴 À développer |
| Tests | 🔴 À développer |
| Déploiement | 🔴 À préparer |

---

# 📜 Licence

La licence du projet sera définie ultérieurement.

---

# 👨🏽‍💻 Projet

**Nom de travail :** À définir  
**Auteur :** Ir. Rossy Wanose  
**Domaine :** Gestion médicale, administrative et financière  
**Statut :** En conception

---

> Ce README constitue la base documentaire du projet. Les décisions techniques détaillées, les modèles de données, les règles métier et les contrats API seront documentés au fur et à mesure de l'avancement du développement.
