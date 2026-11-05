import http from 'k6/http';

const BASE = __ENV.BASE_URL || 'http://localhost';

// Одновременно работают 10 виртуальных пользователей
// Каждый непрерывно отправляет GET-запросы, один за другим, в течение 30 секунд
export const options = {
  vus: Number(__ENV.VUS || 10),
  duration: '30s',
};

// Отправляет GET-запрос
export default function () {
  http.get(`${BASE}/bench-link`, { redirects: 0 }); // Редиректы отключены
}