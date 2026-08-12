// @ts-check
import { defineConfig } from 'astro/config';

const baseDomain = process.env.BASE_DOMAIN;
const site = baseDomain ? `https://lmia.${baseDomain}` : 'http://localhost:30003';

export default defineConfig({
	site,
	server: { port: 30003 },
	vite: {
		ssr: {
			noExternal: [
				'@fontsource-variable/fraunces',
				'@fontsource-variable/source-serif-4',
			],
		},
	},
});

