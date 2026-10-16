import {createApp} from 'vue';
import {createPinia} from 'pinia';
import VisualCheckApp from './components/VisualCheckApp.vue';
import './chartGrid.css';

createApp(VisualCheckApp).use(createPinia()).mount('#app');

const style = document.createElement('style');
style.textContent = '*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#172133;font:14px system-ui}';
document.head.append(style);
