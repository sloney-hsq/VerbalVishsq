import {createApp} from 'vue';
import {createPinia} from 'pinia';
import VisualCheckApp from './components/VisualCheckApp.vue';
import './chartGrid.css';
import './workspaceTheme.css';

createApp(VisualCheckApp).use(createPinia()).mount('#app');
