import http from 'k6/http';

const BASE = __ENV.BASE_URL || 'http://localhost';

export const options = {
  vus: Number(__ENV.VUS || 10),
  duration: '30s',
};

// Подготовка тестовых данных
export function setup() {
  const codes = [];

  // Создает 100 коротких ссылок через API и сохраняет их коды
  for (let i = 0; i < 100; i++) {
    const res = http.post(
      `${BASE}/shorten`,
      JSON.stringify({ original_url: 'https://example.com/' }),
      { headers: { 'Content-Type': 'application/json' } },
    );

    // Извлекает короткий код из URL, полученного в ответе API
    codes.push(res.json('short_url').split('/').pop());
  }

  // Передает коды каждому виртуальному пользователю
  return codes;
}

export default function (codes) {
  // Выбирает случайную короткую ссылку из подготовленных 100
  const code = codes[Math.floor(Math.random() * codes.length)];

  // Отправляет GET-запрос
  http.get(`${BASE}/${code}`, { redirects: 0 });
}