# Подключение MiniRSS к GitHub

MiniRSS проверяет обновления через GitHub Releases. Репозиторий должен быть публичным; токен и отдельный сервер не нужны.

## 1. Создать репозиторий

На GitHub нажмите **New repository**, задайте имя (например, `minirss`) и выберите **Public**. При создании не добавляйте README или .gitignore — они уже лежат в папке проекта.

## 2. Загрузить исходный проект

Откройте терминал в папке `minirss_windows`, в которой лежит `mini_rss.py`, и выполните команды, заменив `YOUR_USERNAME` на свой логин GitHub:

```powershell
git init
git add .
git commit -m "MiniRSS 1.3.0"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/minirss.git
git push -u origin main
```

## 3. Опубликовать первую версию

```powershell
git tag v1.3.0
git push origin v1.3.0
```

Перейдите во вкладку **Actions** репозитория. Workflow `Build and publish MiniRSS for Windows` автоматически выполнит тесты, соберёт Windows EXE и создаст GitHub Release с ZIP-пакетом и SHA-256 файлом.

## 4. Подключить приложение

В MiniRSS откройте **Настройки → Обновления через GitHub** и введите:

```text
YOUR_USERNAME/minirss
```

Включите ежедневную автоматическую проверку. После выхода нового релиза MiniRSS предложит обновление.

## 5. Выпускать дальнейшие версии

1. В `mini_rss.py` увеличьте `APP_VERSION`, например до `1.3.1`.
2. Внесите изменения и отправьте коммит в `main`.
3. Создайте и отправьте тег, равный номеру версии:

```powershell
git add .
git commit -m "MiniRSS 1.3.1"
git push origin main
git tag v1.3.1
git push origin v1.3.1
```

Тег и `APP_VERSION` должны совпадать. Workflow проверяет это до сборки. Приложение читает последний опубликованный Release, находит `MiniRSS_1.3.1_win64.zip` и соответствующий `.sha256`, затем проверяет пакет перед установкой.
