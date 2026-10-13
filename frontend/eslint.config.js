import js from '@eslint/js';
import globals from 'globals';
import hooks from 'eslint-plugin-react-hooks';
import refresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
export default tseslint.config({ignores: ['dist', 'node_modules']}, js.configs.recommended, ...tseslint.configs.recommended, {files: ['**/*.{ts,tsx}'], languageOptions: {globals: globals.browser}, plugins: {'react-hooks': hooks, 'react-refresh': refresh}, rules: {...hooks.configs['recommended-latest'].rules, 'react-refresh/only-export-components': ['warn', {allowConstantExport: true}], 'react-hooks/set-state-in-effect': 'off'}});
