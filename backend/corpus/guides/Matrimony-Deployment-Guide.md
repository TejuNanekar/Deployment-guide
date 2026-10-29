# Matrimony Deployment Guide

Transcribed from Matrimony-Deployment-Guide.pdf (23 Oct 2026).
Line breaks that the PDF inserted inside commands are joined back together so each command can be copied as one line.
Step-by-step commands to take a change from your laptop to the UAT server (anupamshaadi.in) for all five apps, plus where every file lives on the server.

## [locations|api,ui,legacy-admin,legacy-api,legacy-portal,shared] Where the server is

Server: anupamshaadi.in (AlmaLinux 10). Log in with ssh root@anupamshaadi.in. All apps sit behind one Nginx container.

## [locations|api] Where the Backend API lives

Backend API (Spring Boot). URL: https://anupamshaadi.in/api. Local folder: D:\WORK\Weoto\Anupam backend\matrimony-platform. Code on server: container matrimony-api (image ghcr.io/weototechnologies/matrimony-api:<sha>). Settings / passwords: /etc/apps/matrimony/app.env. Logs: podman logs -f matrimony-api.

## [locations|ui] Where the Frontend UI lives

Frontend UI (React). URL: https://anupamshaadi.in/. Local folder: D:\WORK\Weoto\Anupam backend\matrimony-platform-ui. Code on server: /opt/apps/matrimony/ui/current (link to ui/releases/<tag>/). Settings are baked into the build from GitHub repo secrets. Logs: podman logs -f nginx.

## [locations|legacy-admin] Where the Legacy Admin lives

Legacy Admin (CI3). URL: https://admin.anupamshaadi.in/. Local folder: D:\WORK\Weoto\anupam-admin-legacy\anupam-legacy-admin\anupam-admin-main. Code on server: /opt/apps/legacy/anupam-admin/current. Settings: /etc/apps/legacy/anupam-admin/app.env. Logs: /opt/apps/legacy/anupam-admin/shared/logs.

## [locations|legacy-api] Where the Legacy API lives

Legacy API (CI4). URL: https://api.anupamshaadi.in/. Local folder: anupam_api-main. Code on server: /opt/apps/legacy/anupam-api/current. Settings: /etc/apps/legacy/anupam-api/app.env. Logs: /opt/apps/legacy/anupam-api/shared/writable/logs. The Legacy API folder in the platform repo (legacy/API) is an old cPanel copy. Do not deploy it as it is.

## [locations|legacy-portal] Where the Legacy Portal lives

Legacy Portal (CI4). URL: https://anupamshaadi.in/anupamshaadi-new-app/. Local folder: anupam_portal-main. Code on server: /opt/apps/legacy/anupam-portal/current. Settings: /etc/apps/legacy/anupam-portal/app.env. Logs: /opt/apps/legacy/anupam-portal/shared/writable/logs. The Legacy Portal folder in the platform repo (legacy/Web) is an old cPanel copy. Do not deploy it as it is.

## [locations|shared] Other server locations

/opt/apps/stack/compose.yaml defines containers: nginx, matrimony-api, matrimony-valkey, matrimony-mysql. /opt/apps/stack/nginx/conf.d/ holds Nginx site configs (matrimony.conf, anupam-admin.conf, anupam-api.conf, anupam-portal.inc). /opt/apps/matrimony/incoming/ holds UI bundles uploaded by GitHub Actions. /root/stack-files/ holds deploy scripts and the legacy/ folder where you upload legacy .tar.gz files. /root/stack-files/legacy/env/ is the master copy of legacy .app.env files (the script copies them to /etc/apps/legacy/). /opt/apps/legacy/anupam-admin/shared/uploads holds admin user photos and is never overwritten by a deploy. /usr/local/sbin/deploy-app deploys the Matrimony API and UI only. /var/lib/apps/matrimony/mysql holds MySQL data (database shadi, used by all apps). /var/backups/matrimony/mysql holds daily MySQL backups, 02:00 UTC, last 7 kept. /etc/letsencrypt/live/ holds SSL certificates.

## [deploy|api|note] Before you deploy the Backend API

No JAR to copy. GitHub Actions builds a Docker/Podman image and the server pulls it. Downtime: under 1 minute.

## [deploy|api] Step 1 — Local (PowerShell): build and test

Build and test on your laptop before you push.

```powershell
cd "D:\WORK\Weoto\Anupam backend\matrimony-platform"
mvn clean package -DskipTests
mvn spring-boot:run
```

## [deploy|api] Step 2 — Local (PowerShell): push code

Push the API branch that the UAT workflow deploys.

```powershell
git add .
git commit -m "your change"
git push origin development
```

The API branch is development.

## [deploy|api] Only if you added a database column or table — Local (PowerShell): copy the SQL up first

Added a new DB column or table? Run the SQL on the server before the GitHub deploy. Hibernate is set to validate, so the API will not start without it. Copy the .sql up first.

```powershell
scp V5__your_change.sql root@anupamshaadi.in:/root/
```

Skip this step when the change does not add a column or table.

## [deploy|api] Only if you added a database column or table — Server: apply the SQL before the GitHub deploy

Run this on the server before Step 3 — GitHub: run deploy. Skip it when the change does not add a column or table.

```bash
ssh root@anupamshaadi.in
systemctl start matrimony-mysql-backup.service
podman exec -i matrimony-mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot shadi' < /root/V5__your_change.sql
```

## [deploy|api] Step 3 — GitHub: run deploy

1. Open https://github.com/WeotoTechnologies/matrimony-platform/actions
2. Click Deploy API (UAT) > Run workflow > branch development > Run workflow.
3. Wait for the green tick (about 5–10 min). Red = open the run and read the error.

The workflow runs sudo /usr/local/sbin/deploy-app matrimony api <commit-sha> on the server. If the new API does not start within 2 minutes, it switches back to the old one by itself.

## [deploy|api] Step 4 — Server: check

On the server, as root, confirm the new API is the one that is running.

```bash
ssh root@anupamshaadi.in
podman ps
podman logs --tail 100 matrimony-api
curl -fkSs https://127.0.0.1/api/ajax/membership-plan -H 'Host: anupamshaadi.in' >/dev/null && echo api-ok
```

The command prints api-ok.

## [deploy|ui|note] Before you deploy the Frontend UI

No dist/ to copy. GitHub Actions builds it, uploads it and switches the site. No downtime. If backend and frontend both changed, deploy the backend first.

## [deploy|ui] Step 1 — Local (PowerShell): build and test

Build and test the UI on your laptop before you push.

```powershell
cd "D:\WORK\Weoto\Anupam backend\matrimony-platform-ui"
npm ci
npm run lint
npm run build
```

## [deploy|ui] Step 2 — Local (PowerShell): push code

Push the UI branch that the UAT workflow deploys. The UI branch is dev, not development.

```powershell
git add .
git commit -m "your change"
git push origin dev
```

## [deploy|ui] Step 3 — GitHub: run deploy

1. Open https://github.com/WeotoTechnologies/matrimony-platform-ui/actions
2. Click Deploy UI (UAT) > Run workflow > branch dev > Run workflow.
3. Wait for the green tick (about 3–5 min).

The workflow uploads matrimony-ui-<tag>.tar.gz to /opt/apps/matrimony/incoming/, then deploy-app unpacks it to /opt/apps/matrimony/ui/releases/<tag>/ and points ui/current at it.

## [deploy|ui] Step 4 — Server: check

On the server, as root, confirm the new UI release is current. Then open https://anupamshaadi.in in the browser and press Ctrl+F5.

```bash
ssh root@anupamshaadi.in
ls -l /opt/apps/matrimony/ui/current
ls -1t /opt/apps/matrimony/ui/releases
curl -fkSs https://127.0.0.1/ -H 'Host: anupamshaadi.in' >/dev/null && echo ui-ok
```

The command prints ui-ok.

## [deploy|legacy-admin,legacy-api,legacy-portal|note] Before you deploy a legacy app

No GitHub Actions. You make a .tar.gz, upload it, and run one script on the server. Do only the app you changed. File names must be exactly anupam-admin.tar.gz, anupam-api.tar.gz, or anupam-portal.tar.gz.

## [deploy|legacy-admin|note] Legacy Admin code that must already be in place

These lines must be in the code, or the app shows a blank 500 or talks to the live .com site. Admin: application/config/legacy_env.php exists and is included by config.php and database.php. No real .env file inside the folder.

## [deploy|legacy-api|note] Legacy API code that must already be in place

These lines must be in the code, or the app shows a blank 500 or talks to the live .com site. API public/index.php: require FCPATH . '../app/Config/Paths.php'; (not api_ci / web_ci). No real .env file inside the folder. The legacy/API folder in the platform repo is an old cPanel copy. Do not deploy it as it is.

## [deploy|legacy-portal|note] Legacy Portal code that must already be in place

These lines must be in the code, or the app shows a blank 500 or talks to the live .com site. Portal public/index.php: require FCPATH . '../app/Config/Paths.php'; (not api_ci / web_ci). Portal app/Config/Constants.php: API_URL and BASE_URL read from $_ENV. No real .env file inside the folder. The legacy/Web folder in the platform repo is an old cPanel copy. Do not deploy it as it is.

## [deploy|legacy-admin] Step 1 — Local (PowerShell): make the admin tar.gz

Run from the folder that contains anupam-admin-main.

```powershell
cd "D:\WORK\Weoto\anupam-admin-legacy\anupam-legacy-admin"
tar -czf anupam-admin.tar.gz --exclude='anupam-admin-main/uploads' --exclude='anupam-admin-main/application/logs' --exclude='anupam-admin-main/application/cache' --exclude='anupam-admin-main/error_log' --exclude='anupam-admin-main/info.php' --exclude='anupam-admin-main/phpinfo.php' --exclude='anupam-admin-main/mail_test.php' anupam-admin-main
```

## [deploy|legacy-api] Step 1 — Local (PowerShell): make the API tar.gz

Run from the folder that contains anupam_api-main.

```powershell
tar -czf anupam-api.tar.gz --exclude='anupam_api-main/vendor' --exclude='anupam_api-main/writable' --exclude='anupam_api-main/.env' anupam_api-main
```

## [deploy|legacy-portal] Step 1 — Local (PowerShell): make the portal tar.gz

Run from the folder that contains anupam_portal-main.

```powershell
tar -czf anupam-portal.tar.gz --exclude='anupam_portal-main/vendor' --exclude='anupam_portal-main/writable' --exclude='anupam_portal-main/.env' anupam_portal-main
```

## [deploy|legacy-admin] Step 2 — Local (PowerShell): upload the admin archive

Upload only the app you changed.

```powershell
scp anupam-admin.tar.gz root@anupamshaadi.in:/root/stack-files/legacy/
```

## [deploy|legacy-api] Step 2 — Local (PowerShell): upload the API archive

Upload only the app you changed.

```powershell
scp anupam-api.tar.gz root@anupamshaadi.in:/root/stack-files/legacy/
```

## [deploy|legacy-portal] Step 2 — Local (PowerShell): upload the portal archive

Upload only the app you changed.

```powershell
scp anupam-portal.tar.gz root@anupamshaadi.in:/root/stack-files/legacy/
```

## [deploy|legacy-admin,legacy-api,legacy-portal] Step 3 — Server: run the deploy script

On the server, as root.

```bash
ssh root@anupamshaadi.in
cd /root/stack-files
bash deploy-legacy.sh
```

It ends with Done. Verify:. It copies code into /opt/apps/legacy/<app>/current, runs composer install for API and Portal, reloads PHP-FPM and Nginx. User uploads, the database and the Matrimony API are not touched. If it stops with an error, nothing after that line ran; fix and run it again.

## [deploy|legacy-admin] Step 4 — Server: check the admin

Then in the browser, log in to https://admin.anupamshaadi.in/.

```bash
ssh root@anupamshaadi.in
curl -fsS -o /dev/null -H 'Host: admin.anupamshaadi.in' https://127.0.0.1/ && echo admin-ok
```

The command prints admin-ok. There is no automatic rollback for legacy apps. Keep the previous .tar.gz on your PC; to undo, upload it again and re-run Step 3.

## [deploy|legacy-api] Step 4 — Server: check the legacy API

```bash
ssh root@anupamshaadi.in
curl -fsS -o /dev/null -H 'Host: api.anupamshaadi.in' https://127.0.0.1/ && echo legacy-api-ok
```

The command prints legacy-api-ok. There is no automatic rollback for legacy apps. Keep the previous .tar.gz on your PC; to undo, upload it again and re-run Step 3.

## [deploy|legacy-portal] Step 4 — Server: check the portal

Then in the browser, open https://anupamshaadi.in/anupamshaadi-new-app/.

```bash
ssh root@anupamshaadi.in
curl -fsS -o /dev/null -H 'Host: anupamshaadi.in' https://127.0.0.1/anupamshaadi-new-app/ && echo portal-ok
```

The command prints portal-ok. There is no automatic rollback for legacy apps. Keep the previous .tar.gz on your PC; to undo, upload it again and re-run Step 3.

## [settings|api] Local (Git Bash): push API settings

No code deploy is needed. Never commit .env, .env.uat or any app.env file to git. Edit matrimony-platform/.env.uat (KEY=value, no quotes, no $). Git Bash in matrimony-platform installs /etc/apps/matrimony/app.env, restarts the API, and restores the old file if the API fails.

```bash
deploy/push-env.sh .env.uat
```

## [settings|ui] GitHub: change UI settings

Edit the GitHub repo secret in matrimony-platform-ui > Settings > Secrets and variables > Actions. Then run Deploy UI (UAT) again.

## [settings|legacy-admin] Server: change Legacy Admin settings

Edit /root/stack-files/legacy/env/anupam-admin.app.env on the server, then run the legacy deploy script. Never commit an app.env file to git.

```bash
ssh root@anupamshaadi.in
cd /root/stack-files
bash deploy-legacy.sh
```

## [settings|legacy-api] Server: change Legacy API settings

Edit /root/stack-files/legacy/env/anupam-api.app.env on the server, then run the legacy deploy script. Never commit an app.env file to git.

```bash
ssh root@anupamshaadi.in
cd /root/stack-files
bash deploy-legacy.sh
```

## [settings|legacy-portal] Server: change Legacy Portal settings

Edit /root/stack-files/legacy/env/anupam-portal.app.env on the server, then run the legacy deploy script. Never commit an app.env file to git.

```bash
ssh root@anupamshaadi.in
cd /root/stack-files
bash deploy-legacy.sh
```

## [settings|shared] Server: reload Nginx after a config change

Edit /opt/apps/stack/nginx/conf.d/<file> on the server, then test and reload Nginx.

```bash
ssh root@anupamshaadi.in
podman exec nginx nginx -t && podman exec nginx nginx -s reload
```

## [operations|api,ui,legacy-admin,legacy-api,legacy-portal,shared] Server: see running containers

Run as root after ssh root@anupamshaadi.in.

```bash
ssh root@anupamshaadi.in
podman ps
```

## [operations|api] Server: Backend API logs

```bash
ssh root@anupamshaadi.in
podman logs -f matrimony-api
```

## [operations|ui,shared] Server: Nginx logs

```bash
ssh root@anupamshaadi.in
podman logs -f nginx
```

## [operations|legacy-admin,legacy-api,legacy-portal] Server: PHP logs

```bash
ssh root@anupamshaadi.in
journalctl -u php-fpm -f
```

## [operations|api] Server: restart the Backend API

```bash
ssh root@anupamshaadi.in
cd /opt/apps/stack && podman-compose up -d --force-recreate matrimony-api
```

## [operations|ui,shared] Server: restart Nginx

```bash
ssh root@anupamshaadi.in
podman exec nginx nginx -s reload
```

## [operations|legacy-admin,legacy-api,legacy-portal] Server: restart PHP

```bash
ssh root@anupamshaadi.in
systemctl reload php-fpm
```

## [operations|api] Server: list backend versions kept for rollback

The last 5 backend images are kept, so rollback works only for those.

```bash
ssh root@anupamshaadi.in
podman images ghcr.io/weototechnologies/matrimony-api
```

## [operations|api] Server: roll back the Backend API

```bash
ssh root@anupamshaadi.in
deploy-app matrimony api <older-sha>
```

## [operations|ui] Server: list UI versions kept for rollback

The last 5 UI releases are kept, so rollback works only for those.

```bash
ssh root@anupamshaadi.in
ls -1t /opt/apps/matrimony/ui/releases
```

## [operations|ui] Server: roll back the Frontend UI

```bash
ssh root@anupamshaadi.in
deploy-app matrimony ui <older-tag>
```

## [operations|api,ui,legacy-admin,legacy-api,legacy-portal,shared] Server: back up the database now

```bash
ssh root@anupamshaadi.in
systemctl start matrimony-mysql-backup.service
```

## [operations|api,ui,legacy-admin,legacy-api,legacy-portal,shared] Server: open the MySQL shell

```bash
ssh root@anupamshaadi.in
podman exec -it matrimony-mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot shadi'
```

## [operations|api,ui,legacy-admin,legacy-api,legacy-portal,shared] Server: disk space

```bash
ssh root@anupamshaadi.in
df -h
```

## [operations|api,ui,legacy-admin,legacy-api,legacy-portal,shared] Server: memory per container

```bash
ssh root@anupamshaadi.in
podman stats --no-stream
```
