# Design system GahamBani

## Modifier l’identité visuelle

- Couleurs brutes et échelles : `tokens.ts`
- Couleurs sémantiques des modes clair/sombre : `theme.ts`
- Typographie, espacements, rayons, tailles et ombres : `tokens.ts`
- Activation globale et choix clair/sombre : `theme-provider.tsx`

Les écrans utilisent `useAppTheme()` et les composants de `@/components/ui`.
Ils ne doivent pas importer `palette` ni écrire de couleur ou de taille de texte
en dur.

Pour adopter plus tard une police personnalisée :

1. ajouter les fichiers de police dans `assets/fonts`;
2. les intégrer avec le plugin `expo-font` dans `app.json`;
3. remplacer uniquement les valeurs de `fontFamilies` dans `tokens.ts`.

## Composants disponibles

- `AppText` : variantes typographiques et tons sémantiques ;
- `AppButton` : primaire, secondaire, danger, ghost, chargement ;
- `AppInput` : label, aide et erreur ;
- `AppCard` : surface standard ou élevée ;
- `AppBadge` : états neutre, info, succès, avertissement et danger ;
- `EmptyState` : état vide avec action optionnelle ;
- `Screen` : zone sûre, largeur et marges cohérentes.

Les nouveaux composants génériques doivent être ajoutés dans `components/ui`.
Les composants propres à un domaine métier vont dans `features/<domaine>`.
