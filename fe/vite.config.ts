import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// base './' : çıktı, S3 bucket'ının kökünde de bir alt klasöründe de çalışır.
export default defineConfig({ plugins: [react()], base: './' });
