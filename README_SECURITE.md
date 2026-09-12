# 🏥 Plateforme de Gestion du Centre Médical (AFYA - APP)

**Auteur :** Ir. Rossy Wanose --- Future Ingénieur Logiciel\
**Statut :** Conception --- Version 1.0\
**Objectif :** construire une plateforme web moderne, modulaire et
sécurisée pour centraliser la gestion d'un centre médical.

------------------------------------------------------------------------

## 1. Présentation

La plateforme doit permettre de gérer dans une même application :

-   les patients ;
-   les consultations et prestations ;
-   les séances et le suivi des soins ;
-   les paiements, dettes et créances ;
-   la pharmacie et le stock ;
-   le laboratoire ;
-   les soins à domicile ;
-   les rendez-vous et le calendrier ;
-   les rapports et exports ;
-   la messagerie interne ;
-   les utilisateurs, rôles et permissions ;
-   les notifications ;
-   la configuration générale du centre ;
-   la traçabilité des actions.

Le système doit être conçu avec une priorité claire : **la sécurité,
l'intégrité des données et la traçabilité ne doivent pas être ajoutées à
la fin du projet.**

------------------------------------------------------------------------

# 2. Objectifs du projet

## 2.1 Objectif général

Mettre en place une application web permettant au personnel autorisé de
gérer les activités administratives, financières et opérationnelles du
centre médical depuis une interface centralisée.

## 2.2 Objectifs spécifiques

La plateforme doit permettre notamment de :

1.  enregistrer et rechercher les patients ;
2.  suivre les consultations, prestations et séances ;
3.  gérer les paiements et les soldes ;
4.  gérer les dettes et créances ;
5.  gérer les produits, ventes et mouvements de stock de la pharmacie ;
6.  gérer les examens de laboratoire ;
7.  gérer les prestations de soins à domicile ;
8.  gérer les rendez-vous ;
9.  produire des rapports ;
10. communiquer via une messagerie interne ;
11. contrôler précisément les accès ;
12. conserver un historique des actions importantes ;
13. protéger les données sensibles ;
14. sauvegarder les données et permettre une restauration contrôlée.

------------------------------------------------------------------------

# 3. Principes de sécurité

## 3.1 Sécurité dès la conception

La sécurité doit être considérée comme une exigence fonctionnelle et
technique du projet.

Les règles importantes doivent être appliquées **côté serveur**, et non
uniquement dans l'interface JavaScript.

L'utilisateur ne doit jamais pouvoir contourner une permission en
modifiant une requête HTTP, un paramètre JavaScript ou une valeur
envoyée au serveur.

## 3.2 Authentification

L'application doit prévoir :

-   mots de passe stockés avec le mécanisme sécurisé de Django ;
-   sessions sécurisées ;
-   expiration appropriée des sessions ;
-   déconnexion ;
-   protection CSRF ;
-   limitation des tentatives de connexion ;
-   politique de mot de passe ;
-   récupération de compte sécurisée ;
-   possibilité d'activer une authentification renforcée pour les
    comptes privilégiés.

Les secrets techniques ne doivent jamais être écrits directement dans le
code source.

## 3.3 Autorisation

Le système doit appliquer le principe du **moindre privilège**.

Un utilisateur ne reçoit que les droits nécessaires à son travail.

Les permissions peuvent être organisées autour d'actions telles que :

-   consulter ;
-   créer ;
-   modifier ;
-   supprimer ;
-   exporter ;
-   approuver ;
-   administrer.

Les permissions sensibles doivent être contrôlées par le backend.

## 3.4 Rôles

Les rôles initiaux peuvent comprendre :

-   Administrateur système ;
-   Directeur ;
-   Assistant manager ;
-   Médecin ;
-   Technicien de laboratoire ;
-   Pharmacien ;
-   Kinésithérapeute ;
-   Personnel autorisé.

Les rôles pourront évoluer selon les besoins du centre.

## 3.5 Séparation des responsabilités

Certaines opérations sensibles doivent être limitées ou soumises à
validation.

Exemples :

-   modification d'une transaction financière clôturée ;
-   annulation d'un paiement ;
-   modification d'un taux de change utilisé pour une opération ;
-   suppression d'un mouvement de stock ;
-   modification d'une configuration financière ;
-   export massif de données ;
-   gestion des comptes utilisateurs.

------------------------------------------------------------------------

# 4. Audit et traçabilité

Les opérations importantes doivent être enregistrées dans un journal
d'audit.

Un événement d'audit peut contenir :

-   utilisateur ;
-   action ;
-   module ;
-   objet concerné ;
-   date et heure ;
-   adresse IP lorsque cela est pertinent ;
-   ancienne valeur lorsque nécessaire ;
-   nouvelle valeur lorsque nécessaire ;
-   résultat de l'opération.

Les journaux d'audit ne doivent pas être modifiables par les
utilisateurs ordinaires.

Il faut éviter d'enregistrer dans les logs techniques :

-   mots de passe ;
-   jetons d'authentification ;
-   secrets ;
-   données médicales inutiles ;
-   informations financières sensibles qui ne sont pas nécessaires au
    diagnostic technique.

------------------------------------------------------------------------

# 5. Architecture technique

Architecture recommandée :

``` text
Utilisateur
    │
    │ HTTPS / WebSocket sécurisé
    ▼
Interface Web
    │
    ▼
Django + Django REST Framework
    │
    ├── Authentification / Autorisation
    ├── Patients
    ├── Centre médical
    ├── Finance
    ├── Pharmacie
    ├── Laboratoire
    ├── Soins à domicile
    ├── Rendez-vous
    ├── Rapports
    ├── Messagerie
    ├── Notifications
    └── Audit
    │
    ├──────────────► PostgreSQL
    │
    ├──────────────► Redis / WebSocket
    │
    └──────────────► Stockage sécurisé des fichiers
```

------------------------------------------------------------------------

# 6. Technologies proposées

## Frontend

-   HTML5 ;
-   Tailwind CSS ;
-   JavaScript.

## Backend

-   Python ;
-   Django ;
-   Django REST Framework ;
-   Django Channels pour les fonctionnalités temps réel.

## Base de données

-   PostgreSQL.

## Temps réel

-   WebSocket ;
-   Redis comme infrastructure de support lorsque nécessaire.

## Documents et exports

-   PDF ;
-   Excel ;
-   Word.

------------------------------------------------------------------------

# 7. Architecture modulaire

Le projet doit rester modulaire afin d'éviter une application
monolithique difficile à maintenir.

Structure proposée :

``` text
medical_center/
│
├── config/
│   ├── settings/
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
│
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
│   ├── notifications/
│   ├── settings_app/
│   └── audit/
│
├── templates/
├── static/
├── media/
├── tests/
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

------------------------------------------------------------------------

# 8. Gestion des patients

Le module patient doit permettre :

-   création ;
-   modification selon permissions ;
-   recherche ;
-   consultation de l'historique ;
-   identification fiable ;
-   prévention des doublons ;
-   rattachement aux prestations ;
-   rattachement aux paiements ;
-   rattachement aux rendez-vous ;
-   rattachement aux examens ;
-   rattachement aux soins à domicile.

Les identifiants techniques doivent être robustes et ne pas reposer
uniquement sur des informations facilement devinables.

------------------------------------------------------------------------

# 9. Consultations, prestations et séances

Le système doit gérer :

-   type de prestation ;
-   patient ;
-   professionnel ;
-   date ;
-   nombre de séances ;
-   séances réalisées ;
-   séances restantes ;
-   montant ;
-   statut ;
-   notes nécessaires au fonctionnement du service.

Le nombre de séances restantes doit être calculé à partir de données
fiables.

Il ne faut pas faire confiance à une valeur librement modifiable envoyée
par le navigateur.

------------------------------------------------------------------------

# 10. Gestion financière

Le module financier doit gérer notamment :

-   factures ;
-   paiements ;
-   reçus ;
-   dépenses ;
-   dettes ;
-   créances ;
-   soldes ;
-   annulations/corrections tracées ;
-   éventuellement remboursements selon les règles du centre.

## 10.1 Multi-devise

Les devises principales sont :

-   USD ;
-   FC.

Chaque transaction financière doit conserver son contexte historique.

Structure conceptuelle minimale :

``` text
montant_original
devise_originale
taux_utilise
montant_converti
devise_de_reference
date_transaction
utilisateur
```

**Règle essentielle :** une modification future du taux de change ne
doit pas recalculer silencieusement les anciennes transactions.

## 10.2 Intégrité financière

Les opérations financières critiques doivent utiliser des transactions
atomiques en base de données lorsque plusieurs écritures doivent être
cohérentes.

Une transaction clôturée ne doit pas être supprimée physiquement comme
si elle n'avait jamais existé.

Pour une correction, privilégier une opération traçable :

``` text
transaction originale
        ↓
annulation / correction
        ↓
nouvelle transaction
        ↓
journal d'audit
```

------------------------------------------------------------------------

# 11. Pharmacie

Le module pharmacie doit gérer :

-   produits ;
-   catégories ;
-   prix ;
-   stock ;
-   ventes ;
-   mouvements de stock ;
-   entrées ;
-   sorties ;
-   dates d'expiration ;
-   alertes ;
-   historique.

Le système doit empêcher les incohérences comme :

-   stock négatif ;
-   sortie supérieure au stock disponible ;
-   suppression non tracée d'un mouvement ;
-   modification silencieuse d'une vente.

------------------------------------------------------------------------

# 12. Laboratoire

Le module laboratoire doit gérer :

-   examens ;
-   patients ;
-   prescripteurs ;
-   montants ;
-   paiements ;
-   résultats ou informations nécessaires au processus ;
-   répartition des revenus ;
-   historique.

## 12.1 Répartition initiale

Selon les règles fonctionnelles prévues :

-   20 % pour le prescripteur ;
-   80 % restant ;
-   sur les 80 % restants :
    -   60 % pour l'équipe du laboratoire ;
    -   40 % pour le centre.

Les pourcentages doivent être configurables avec des permissions
appropriées.

**Important :** lorsqu'une répartition a été appliquée à une opération,
les valeurs historiques calculées doivent être conservées.

Une modification ultérieure de la configuration ne doit pas réécrire
l'historique.

------------------------------------------------------------------------

# 13. Soins à domicile

Le module doit permettre de gérer :

-   patient ;
-   médecin traitant ;
-   service ;
-   séances ;
-   facturation ;
-   paiement ;
-   solde ;
-   répartition ;
-   notes nécessaires.

Les règles financières appliquées doivent être historisées.

------------------------------------------------------------------------

# 14. Rendez-vous et calendrier

Le système doit permettre :

-   création de rendez-vous ;
-   modification ;
-   annulation ;
-   patient ;
-   professionnel ;
-   motif ;
-   date et heure ;
-   rappels ;
-   alarmes ;
-   historique.

Les rappels importants doivent être gérés côté serveur.

Il ne faut pas dépendre uniquement du navigateur ouvert pour exécuter
une notification critique.

------------------------------------------------------------------------

# 15. Rapports

Les rapports doivent pouvoir être produits selon différentes périodes :

-   quotidien ;
-   mensuel ;
-   annuel.

Exemples :

-   recettes ;
-   dépenses ;
-   paiements ;
-   dettes ;
-   créances ;
-   ventes pharmacie ;
-   stock ;
-   laboratoire ;
-   soins à domicile ;
-   activité générale.

Formats prévus :

-   PDF ;
-   Excel ;
-   Word.

L'export doit lui-même être soumis aux permissions.

------------------------------------------------------------------------

# 16. Messagerie interne

Une messagerie interne peut être proposée avec :

-   conversations privées ;
-   groupes ;
-   texte ;
-   emojis ;
-   fichiers ;
-   images ;
-   vidéos ;
-   messages vocaux ;
-   recherche ;
-   mise en forme ;
-   messages temporaires ;
-   messages permanents.

Architecture séparée :

``` text
messaging/
├── conversations
├── members
├── messages
├── attachments
└── permissions
```

## 16.1 Sécurité de la messagerie

Chaque accès à une conversation doit vérifier l'appartenance de
l'utilisateur.

Les fichiers doivent être contrôlés :

-   taille maximale ;
-   type autorisé ;
-   nom sécurisé ;
-   emplacement de stockage ;
-   contrôle d'accès ;
-   téléchargement autorisé uniquement aux utilisateurs concernés.

La messagerie ne doit pas être présentée comme chiffrée de bout en bout
sans conception cryptographique spécifique.

------------------------------------------------------------------------

# 17. Comptes utilisateurs

## 17.1 Ancienne approche à éviter

L'utilisation d'un code de sécurité conservé dans un fichier Excel ou
JSON comme mécanisme principal de création de compte n'est pas
suffisamment robuste pour une application de production.

Un fichier de ce type peut être copié, modifié, exposé ou partagé.

## 17.2 Approche recommandée

Préférer :

``` text
Administrateur
     ↓
Invitation / code temporaire
     ↓
Création du compte
     ↓
Définition du mot de passe
     ↓
Attribution du rôle
     ↓
Journal d’audit
```

Les codes temporaires doivent être :

-   à durée limitée ;
-   révocables ;
-   à usage contrôlé ;
-   stockés de manière sécurisée ;
-   invalidés après utilisation lorsque cela est nécessaire.

------------------------------------------------------------------------

# 18. Tableau de bord

Le tableau de bord doit être adapté au rôle de l'utilisateur.

Exemples :

### Direction

-   recettes ;
-   dépenses ;
-   activité ;
-   dettes ;
-   créances ;
-   indicateurs ;
-   alertes.

### Pharmacie

-   stock ;
-   ruptures ;
-   produits proches de l'expiration ;
-   ventes.

### Laboratoire

-   examens ;
-   activité ;
-   répartition ;
-   recettes.

### Personnel médical

-   patients ;
-   consultations ;
-   séances ;
-   rendez-vous.

------------------------------------------------------------------------

# 19. Notifications

Le système peut notifier :

-   rendez-vous ;
-   rappels ;
-   stock faible ;
-   expiration prochaine ;
-   paiement ;
-   dette ;
-   créance ;
-   nouveau message ;
-   événements administratifs.

Les notifications sensibles doivent respecter les permissions de
l'utilisateur.

------------------------------------------------------------------------

# 20. Configuration générale

La configuration peut comprendre :

-   nom du centre ;
-   logo ;
-   adresse ;
-   email ;
-   téléphone ;
-   personnel ;
-   entreprises ;
-   taux de change ;
-   examens ;
-   services ;
-   pourcentages ;
-   paramètres d'affichage.

Les paramètres ayant un impact financier doivent être particulièrement
protégés et audités.

------------------------------------------------------------------------

# 21. Protection des données et fichiers

Les données sensibles doivent être protégées pendant :

-   le transport ;
-   le stockage ;
-   les sauvegardes ;
-   les exports ;
-   les téléchargements.

L'application doit utiliser HTTPS en production.

Les fichiers importés doivent être contrôlés avant stockage.

Les médias ne doivent pas être accessibles simplement parce qu'une URL
est connue.

Les exports doivent être soumis aux permissions.

------------------------------------------------------------------------

# 22. Sauvegardes et restauration

Prévoir :

-   sauvegardes automatiques PostgreSQL ;
-   plusieurs versions de sauvegarde ;
-   stockage séparé ;
-   sauvegarde des médias ;
-   procédure de restauration ;
-   tests réguliers de restauration.

Une sauvegarde qui n'a jamais été restaurée en test ne doit pas être
considérée comme pleinement fiable.

------------------------------------------------------------------------

# 23. Règles métier et gestion des erreurs

Le backend doit refuser notamment :

-   accès non autorisé ;
-   paiement incohérent ;
-   stock négatif ;
-   pourcentage invalide ;
-   opération financière impossible ;
-   nombre de séances impossible ;
-   modification non autorisée d'une opération clôturée ;
-   accès à une conversation sans appartenance ;
-   fichier non autorisé.

En cas d'erreur dans une opération composée de plusieurs étapes, les
écritures doivent être annulées lorsque nécessaire afin d'éviter un état
partiellement enregistré.

------------------------------------------------------------------------

# 24. Base de données

Principes :

-   PostgreSQL ;
-   clés étrangères ;
-   contraintes ;
-   index adaptés ;
-   dates de création/modification ;
-   suppression protégée lorsque nécessaire ;
-   identifiants robustes ;
-   types décimaux pour les montants financiers ;
-   contraintes d'intégrité ;
-   historique des opérations critiques.

Entités principales envisagées :

``` text
User
Role
Permission
Patient
Company
Staff
Service
Session
Invoice
Payment
Expense
Debt
Receivable
ExchangeRate
PharmacyProduct
StockMovement
LaboratoryExam
LaboratoryService
HomeCareService
Appointment
Conversation
ConversationMember
Message
MessageAttachment
Notification
AuditLog
Report
```

------------------------------------------------------------------------

# 25. Variables d'environnement

Les secrets doivent être séparés du code.

Exemple de `.env.example` :

``` env
SECRET_KEY=
DEBUG=False
ALLOWED_HOSTS=
DATABASE_URL=
REDIS_URL=
```

Ne jamais versionner :

``` text
.env
mot de passe
clé secrète
jeton
identifiants de production
certificats privés
sauvegardes contenant des données sensibles
```

------------------------------------------------------------------------

# 26. Tests

Le projet doit prévoir :

## Tests unitaires

Tester les règles métier isolées.

## Tests d'intégration

Tester les interactions entre modules et la base de données.

## Tests API

Tester les endpoints avec différents rôles.

## Tests de sécurité

Vérifier notamment :

-   accès sans authentification ;
-   accès avec mauvais rôle ;
-   élévation de privilèges ;
-   CSRF ;
-   contrôle des fichiers ;
-   accès aux ressources d'un autre patient ;
-   accès aux conversations privées ;
-   manipulation des montants ;
-   manipulation des permissions.

------------------------------------------------------------------------

# 27. Développement par phases

## Phase 1 --- Fondations

-   création du projet Django ;
-   PostgreSQL ;
-   configuration ;
-   environnement ;
-   structure modulaire ;
-   Git.

## Phase 2 --- Sécurité et comptes

-   authentification ;
-   rôles ;
-   permissions ;
-   sessions ;
-   audit ;
-   récupération de compte.

## Phase 3 --- Patients

-   patients ;
-   recherche ;
-   historique ;
-   prestations.

## Phase 4 --- Finance

-   factures ;
-   paiements ;
-   dettes ;
-   créances ;
-   multi-devise ;
-   reçus ;
-   audit financier.

## Phase 5 --- Pharmacie, laboratoire et soins à domicile

-   stock ;
-   ventes ;
-   examens ;
-   répartitions ;
-   soins.

## Phase 6 --- Rendez-vous

-   calendrier ;
-   rappels ;
-   notifications.

## Phase 7 --- Rapports

-   statistiques ;
-   PDF ;
-   Excel ;
-   Word.

## Phase 8 --- Messagerie

-   conversations ;
-   messages ;
-   fichiers ;
-   temps réel ;
-   permissions.

## Phase 9 --- Durcissement

-   tests de sécurité ;
-   sauvegardes ;
-   restauration ;
-   logs ;
-   contrôle des accès ;
-   préparation production.

------------------------------------------------------------------------

# 28. Organisation Git

Branches recommandées :

``` text
main
develop
feature/*
fix/*
security/*
```

Les changements importants doivent être revus avant intégration.

Les modifications de sécurité doivent être traitées avec une attention
particulière.

------------------------------------------------------------------------

# 29. Critères de qualité avant production

L'application ne doit pas être considérée comme prête uniquement parce
que les pages fonctionnent.

Avant mise en production, vérifier :

-   authentification ;
-   permissions backend ;
-   audit ;
-   HTTPS ;
-   secrets ;
-   sauvegardes ;
-   restauration ;
-   intégrité financière ;
-   sécurité des fichiers ;
-   sécurité des exports ;
-   tests ;
-   gestion des erreurs ;
-   protection contre les accès horizontaux entre patients/utilisateurs
    ;
-   limitation des opérations sensibles.

------------------------------------------------------------------------

# 30. État du projet

  Domaine                   État
  ------------------------- ------------------
  Cahier fonctionnel        🟡 En conception
  Architecture              🟡 À finaliser
  Base de données           🟡 À modéliser
  Authentification          🔴 À développer
  Permissions               🔴 À développer
  Audit                     🔴 À développer
  Patients                  🔴 À développer
  Finance                   🔴 À développer
  Pharmacie                 🔴 À développer
  Laboratoire               🔴 À développer
  Soins à domicile          🔴 À développer
  Rendez-vous               🔴 À développer
  Rapports                  🔴 À développer
  Messagerie                🔴 À développer
  Tests de sécurité         🔴 À développer
  Sauvegarde/restauration   🔴 À développer

------------------------------------------------------------------------

# 31. Décisions importantes

Les principes suivants sont considérés comme non négociables pour la
conception :

1.  **Le backend est l'autorité finale.**
2.  **Une permission ne doit jamais être uniquement visuelle.**
3.  **Les transactions financières doivent conserver leur contexte
    historique.**
4.  **Les opérations critiques doivent être traçables.**
5.  **Les fichiers sensibles doivent être protégés.**
6.  **Les secrets ne doivent pas être stockés dans le dépôt Git.**
7.  **Les comptes privilégiés doivent bénéficier d'une protection
    renforcée.**
8.  **Les sauvegardes doivent être testées par restauration.**
9.  **Une correction financière doit rester traçable.**
10. **La sécurité doit être testée avant la mise en production.**

------------------------------------------------------------------------

# 32. Prochaine étape technique

La prochaine étape recommandée est de construire le **modèle de données
complet**, avant de développer toutes les interfaces.

Il faudra notamment définir précisément :

-   utilisateurs ;
-   rôles ;
-   permissions ;
-   patients ;
-   personnel ;
-   services ;
-   séances ;
-   factures ;
-   paiements ;
-   dépenses ;
-   dettes ;
-   créances ;
-   devises ;
-   taux de change ;
-   produits ;
-   mouvements de stock ;
-   examens ;
-   répartitions ;
-   rendez-vous ;
-   conversations ;
-   messages ;
-   pièces jointes ;
-   notifications ;
-   journal d'audit.

Cette modélisation servira ensuite de base au développement Django, aux
API, aux permissions et aux tests.

------------------------------------------------------------------------

## Conclusion

Ce cahier des charges conserve les fonctionnalités principales du projet
tout en renforçant les aspects qui conditionnent réellement sa fiabilité
: **sécurité, permissions, audit, intégrité financière, protection des
fichiers, sauvegarde et architecture modulaire**.

L'objectif n'est pas seulement de créer une application qui fonctionne,
mais une application dont les données et les opérations importantes
peuvent être **contrôlées, expliquées, restaurées et auditées**.

## Nom de l'App

**AFYA - APP 