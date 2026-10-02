# Brilliant English School ERP — Online Hosting Edition

This package is prepared for browser-based hosting. School computers and phones do not need Python, Flask, SQLite, or any other local installation.

## Recommended hosting

Render Web Service + persistent disk is the simplest first deployment for this SQLite-based edition.

## Deploy

1. Create a GitHub repository and upload all files in this folder.
2. In Render, choose **New → Blueprint** and select the GitHub repository.
3. Render will read `render.yaml`.
4. When prompted for secrets, set:
   - `ADMIN_USERNAME`: your administrator username
   - `ADMIN_PASSWORD`: a strong administrator password
5. Create the service.
6. After deployment, open the generated `https://...onrender.com` URL.
7. Login with the administrator credentials you entered.

## Important

The current edition uses SQLite on a Render persistent disk so existing application code remains compatible. The disk is persistent, but it is attached to one service instance. For a larger multi-instance deployment, migrate the database to Render Postgres.

## Custom domain

After deployment, add a custom domain in Render, for example:

`erp.yourschooldomain.com`

Then update the DNS record at your domain provider as Render instructs.

## Local testing

If you still want to test locally, use START_ERP.bat on Windows. The online version itself does not require local Python on the school computers.
