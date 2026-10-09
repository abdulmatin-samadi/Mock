# DreamZone frontend (Netlify)

`public/static/` holds the site's CSS, JavaScript and images. Django (in `../backend`) renders the
pages and links to these files as `/static/...`.

Netlify (configured by `../netlify.toml`) publishes `public/` and runs `build.sh`, which writes
`public/_redirects` so that every request without a static file is proxied to the Render backend
(`BACKEND_URL`, default `https://dreamzone-samadi-api.onrender.com`).
