# MiniRSS 1.4.0

Компактная RSS/Atom-читалка для Windows 10/11.

## Возможности

- RSS и Atom, подписки, поиск, избранное и автоматическое обновление.
- Три оформления: светлое, тёмное и отдельная тема **iOS 27 · Liquid Glass**.
- Liquid Glass включает светлые стеклянные поверхности, полупрозрачную стилизацию, увеличенные отступы и плавающую нижнюю панель навигации. Исходные темы остаются без изменений.
- Готовые источники новостей из Казахстана, русскоязычных и мировых СМИ, технологий и науки.
- В технологической подборке: Rozetked и iGuides через Google Новости, 4PDA через RSS.
- Компактный режим, прозрачность, режим «поверх окон», системный трей, автозапуск и уведомления.
- Проверка обновлений через GitHub Releases с SHA-256 и резервным восстановлением.

## Запуск и сборка

Для сборки на Windows установите зависимости:

```powershell
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name MiniRSS --icon=assets/minirss.ico --add-data "assets;assets" --collect-all pystray --collect-all winotify --collect-all PIL --hidden-import winotify mini_rss.py
```

Или запустите `build_exe.bat`.

## Репозиторий и релизы

https://github.com/Drakkkkon/MiniRSS

Готовые сборки Windows публикуются в GitHub Releases. Приложение использует этот же репозиторий для проверки обновлений.
