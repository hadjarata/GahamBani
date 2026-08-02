// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*'],
  },
  {
    files: ['src/app/**/*.{ts,tsx}', 'src/features/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: "Literal[value=/^(#(?:[0-9a-fA-F]{3,8})|rgba?\\()/]",
          message: 'Utiliser une couleur sémantique fournie par useAppTheme().',
        },
        {
          selector: "Property[key.name='fontSize'][value.type='Literal']",
          message: 'Utiliser une variante typographique centralisée via AppText.',
        },
        {
          selector: "Property[key.name='lineHeight'][value.type='Literal']",
          message: 'Utiliser une variante typographique centralisée via AppText.',
        },
      ],
    },
  },
]);
