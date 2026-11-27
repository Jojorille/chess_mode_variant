====================================================================
     JEU D'ÉCHECS MULTI-VARIANTES - GUIDE DE DÉMARRAGE
====================================================================

Ce guide explique étape par étape comment lancer et ouvrir le jeu
sur votre ordinateur (Windows).


--------------------------------------------------------------------
ÉTAPE 1 : Préparer l'environnement (à faire une seule fois)
--------------------------------------------------------------------
1. Vérifiez que Python est installé sur votre ordinateur.
2. Ouvrez PowerShell ou l'Invite de commandes (cmd).
3. Rendez-vous dans le dossier du projet en tapant :
   cd /d d:\moi\programe\echec_multi
4. Installez les dépendances nécessaires :
   pip install -r requirements.txt


--------------------------------------------------------------------
ÉTAPE 2 : Lancer le serveur du jeu (Backend Python)
--------------------------------------------------------------------
1. Dans le même terminal (dans le dossier du projet), lancez le
   serveur avec la commande :
   python app.py

   (Alternative : python -m uvicorn app:app --host 0.0.0.0 --port 8000)

2. Vérifiez qu'un message similaire à celui-ci s'affiche :
   Uvicorn running on http://0.0.0.0:8000

IMPORTANT : Laissez cette fenêtre de terminal ouverte pendant toute
la durée de votre partie. Si vous la fermez, le jeu ne pourra plus
communiquer entre les joueurs.


--------------------------------------------------------------------
ÉTAPE 3 : Ouvrir l'interface du jeu dans votre navigateur
--------------------------------------------------------------------
1. Ouvrez l'Explorateur de fichiers Windows et allez dans :
   d:\moi\programe\echec_multi
2. Double-cliquez sur le fichier :
   index.html

   Le jeu s'ouvrira directement dans votre navigateur web par défaut
   (Chrome, Edge, Firefox, etc.).


--------------------------------------------------------------------
ÉTAPE 4 : Créer une partie et jouer à deux (test local)
--------------------------------------------------------------------
1. Sur la page ouverte, choisissez la variante souhaitée dans le
   menu déroulant (Standard, Chess 960, Club House, Fog of War,
   Qui perd gagne, Dame Cachée ou Bataille Chess).
2. Cliquez sur le bouton "Créer une partie".
3. Vous arrivez dans la salle d'attente : cliquez sur
   "Copier le lien".
4. Ouvrez un nouvel onglet (ou une nouvelle fenêtre) dans votre
   navigateur et collez le lien dans la barre d'adresse, puis
   appuyez sur Entrée.
5. Les deux joueurs sont maintenant connectés (Blancs dans le
   premier onglet, Noirs dans le second) et l'échiquier apparaît !


--------------------------------------------------------------------
BONUS : Lancer les tests automatisés du moteur (optionnel)
--------------------------------------------------------------------
Pour vérifier que toutes les règles des 7 variantes fonctionnent
correctement, ouvrez un terminal dans le dossier du projet et lancez :
   python -m unittest test_engine.py


--------------------------------------------------------------------
DÉPANNAGE RAPIDE
--------------------------------------------------------------------
- Le bouton "Créer une partie" ne fait rien :
  Vérifiez que la fenêtre du serveur Python (Étape 2) est bien
  ouverte et tourne sans erreur.
- L'affichage semble bloqué sur une ancienne version :
  Appuyez sur Ctrl + F5 dans votre navigateur pour vider le cache.
- Vous voulez recommencer une partie proprement :
  Cliquez sur "Quitter la partie" ou "Annuler" pour nettoyer la
  session sauvegardée.
====================================================================
