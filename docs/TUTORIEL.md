# Votre premier DCF relu dans Claude, en 10 minutes

Vous allez construire un DCF rapide d'Apple à partir de ses comptes déposés, faire vérifier chaque chiffre contre le
10-K, faire relire et contester le modèle, puis le valider. Aucun terminal n'est nécessaire.

**Il vous faut :**
- Un compte Claude. Les plugins demandent un abonnement payant. Un compte gratuit peut ajouter un connecteur
  personnalisé et utiliser les outils de données, sans les rôles.
- L'exécution de code activée, dans **Paramètres → Capacités**. Les rôles lancent de petits scripts dans le
  bac à sable de Claude.

## 1. Ajouter le connecteur de données (1 minute)

1. **Ouvrez le formulaire :** dans Claude, allez dans **Paramètres → Connecteurs → Ajouter un connecteur personnalisé**.
2. **Remplissez-le :** nommez-le `deskstack` et collez `https://deskstack.deskstack-server.workers.dev/mcp`. Aucune connexion n'est demandée. Vous pouvez
   aussi lancer votre propre copie ([auto-hébergement](SELF_HOSTING.md)).
3. **Vérifiez que ça marche :** demandez *« Avec deskstack, quel a été le chiffre d'affaires d'Apple sur l'exercice
   2025 ? Cite le dépôt. »* La réponse doit citer le 10-K et son numéro d'accession.

## 2. Ajouter l'équipe (1 minute)

1. Allez dans **Personnaliser → Plugins → Ajouter une marketplace**.
2. Collez `https://github.com/joaquimmj/deskstack`.
3. Installez **deskstack**. Les commandes `/analyst`, `/associate`, `/vp-review`, `/md-redteam`, `/compliance`,
   `/sign-off` et `/deal-team` apparaissent.

## 3. Construire le modèle (3 minutes)

Tapez `/analyst Apple quick-dcf`. L'analyste :

1. **Récupère les données.** Il prend les trois derniers exercices dans le 10-K : chiffre d'affaires, résultat
   opérationnel, amortissements, investissements. Il récupère aussi le taux à 10 ans du Trésor américain et la prime
   de risque de Damodaran.
2. **Affiche un tableau d'hypothèses** (croissance, marges, WACC, croissance terminale), chacune avec sa
   justification. **Lisez-le et changez ce qui ne vous convient pas** : c'est votre modèle.
3. **Construit le classeur Excel :**
   - en bleu les saisies, en noir les formules ;
   - une feuille **Sources** cite chaque chiffre saisi ;
   - la couverture indique *Draft for human review. Not investment advice.*
4. **Passe le vérificateur** sur son propre fichier et corrige ce qu'il peut.

Téléchargez le classeur.

## 4. Faire vérifier chaque chiffre (2 minutes)

**Ouvrez une nouvelle conversation,** pour que le relecteur ne voie pas comment le modèle a été construit.
Déposez-y le classeur et tapez `/associate`.

L'associate rapproche chaque chiffre saisi du dépôt officiel. Un rapport typique ressemble à ceci :

| # | Cellule | Ligne | Période | Valeur du modèle | Statut | Valeur déposée | Note |
|---|---|---|---|---|---|---|---|
| 1 | `Inputs!D5` | Chiffre d'affaires | FY2025 | 416 161 000 | mismatch | 416 161 | Échelle : le chiffre correspond s'il est en milliers, pas en millions |
| 2 | `Inputs!C5` | Chiffre d'affaires | FY2024 | 391 035 | match | 391 035 | |

Un **mismatch** dit pourquoi quand il le peut :
- mauvaise unité ;
- signe inversé ;
- chiffre de l'année d'avant ;
- autre ligne ;
- autre devise.

**Not found** signifie que le dépôt ne publie pas cette ligne pour cette période.

## 5. Relire et contester (2 minutes)

Dans la même conversation de relecture :

- **`/vp-review`** lance 21 contrôles automatiques :
  - chiffres tapés dans les formules, et lignes dont la formule sort du motif ;
  - bilan déséquilibré ;
  - valeur terminale au-dessus de 75 % de la valeur d'entreprise, WACC trop proche de la croissance terminale.

  Il compare ensuite vos hypothèses à l'historique déposé d'Apple.
- **`/md-redteam`** argumente contre la valorisation. Donnez-lui le cours du jour : il vous dit ce que le marché
  suppose, par exemple *« à 230 $, le marché suppose un WACC de 6,0 % »*. Il liste aussi les cinq objections les plus
  fortes, avec leur effet sur la valeur par action.
- **`/compliance`** vérifie la tenue : mention de non-conseil, sources, saisies datées, aucun signe d'information non
  publique.

## 6. Corriger, puis valider (1 minute)

1. **Corrigez.** Revenez dans la première conversation, dites à l'analyste quels points corriger, et il reconstruit
   le classeur. Les relecteurs ne modifient jamais votre fichier eux-mêmes.
2. **Validez.** Lancez `/sign-off`. Il affiche une page avec chaque contrôle, chaque point encore ouvert, et un jeton
   d'approbation. Rien n'est exporté tant que vous ne répondez pas avec vos propres mots, par exemple *« J'approuve
   l'export »*. Ensuite :
   - vous recevez une copie avec une feuille **Sign-off**, qui enregistre qui a validé, quand, et ce qui restait
     ouvert ;
   - une réponse comme *« pas encore »* ou *« j'approuve une fois corrigé »* n'est jamais prise pour un accord.

## Le raccourci

`/deal-team Apple quick-dcf` enchaîne toutes ces étapes et s'arrête à la validation pour attendre votre accord. Dans
Claude Code et Cowork, les relecteurs tournent automatiquement comme des agents séparés : pas besoin de nouvelle
conversation.

## En cas de problème

| Symptôme | Que faire |
|---|---|
| « connector not connected » | Vérifiez **Paramètres → Connecteurs** : deskstack doit être *Connecté* |
| Les scripts ne se lancent pas | Activez l'exécution de code dans **Paramètres → Capacités** |
| Une entreprise européenne est introuvable | La couverture compte 229 grands émetteurs dans 14 pays, Royaume-Uni compris, et aucun allemand. Essayez son LEI, ou `/eu-company` |
| Une banque ou un assureur | Un DCF classique ne s'y applique pas. L'analyste propose le PER ou le P/B à la place |
| « Free daily capacity is used up » | Le service partagé repart à 00:00 UTC ; vous pouvez aussi [auto-héberger](SELF_HOSTING.md) |

Tout ce que produit deskstack est un brouillon à faire relire par un humain, pas un conseil en investissement.
