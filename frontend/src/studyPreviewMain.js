import {createApp} from 'vue';
import {createPinia} from 'pinia';
import StudyPreviewApp from './components/StudyPreviewApp.vue';
import './workspaceTheme.css';

createApp(StudyPreviewApp).use(createPinia()).mount('#app');
