# Uutiskeskustelu

Erillinen keskustelupalsta, jonka etusivu näyttää enintään kymmenen juttua. Palvelin tarkistaa IS:n **Nyt**-listan ja IL:n **Juuri nyt** -listan heti käynnistyessä ja sen jälkeen 10 minuutin välein. Selain hakee päivitetyn listan 30 sekunnin välein. Jos palvelin nukkuu, sen oma ajastus jatkuu vasta käynnistyttyään.

Lehtien yhteisiä lukijamääriä ei ole käytettävissä. Yhdistetty lista järjestetään lehden oman sijoituksen mukaan. Tasatilanteessa IS on ensin. Sijoitus omalla listalla näkyy otsikon yläpuolella. Samalla lehdellä tunniste estää saman artikkelin tuonnin kahdesti. Yhdistelmälistalta poistetaan myös otsikot, jotka ovat samat kirjainkoon, välimerkkien ja välilyöntien normalisoinnin jälkeen. Samasta aiheesta eri otsikoilla kirjoitetut jutut voivat näkyä erikseen.

IS:n sivudatasta tarkistetaan artikkelin tunniste, `commentingVisible` ja `commentingEnded`. IL:n sivudatasta tarkistetaan tunniste ja `commenting_enabled`. Myös päättyneet kommentointiketjut kelpaavat. IL:n kenttä kertoo nykyisen tilan. Jos yksittäisen jutun tilaa ei saada vahvistettua, juttu jää pois uudelta listalta. Jos koko lähteen haku epäonnistuu, viimeinen onnistunut lista näkyy päivitysaikoineen ja virheilmoituksella. Vanhat keskustelut säilyvät tietokannassa.

## Mainosbannerit

Laita WebP-kuvat kansioihin `tietokone/mainokset/` ja `mobiili/mainokset/`. Selain käyttää mobiilikansiota, kun näkymä on enintään 600 px leveä. Käytä molemmissa kansioissa samoja nimiä:

- `top.webp` ylätunnisteen alle
- `after-5.webp` viidennen näkyvän uutisen jälkeen
- `after-10.webp` kymmenennen näkyvän uutisen jälkeen

Kuva täyttää banneripaikan leveyden ja säilyttää kuvasuhteensa. Esimerkkikoot ovat tietokoneelle 810 × 100 px ja puhelimelle 350 × 64 px. Jos kyseiseen paikkaan ei ole kuvaa valitussa kansiossa, näkyy teksti **Mainospaikka**.

Muille kuville on varattu kansiot `tietokone/kuvat/`, `mobiili/kuvat/` ja `yhteiset/kuvat/`. Näiden sisältö voidaan ottaa käyttöön, kun kuvat lisätään sivustolle.

## Käynnistys Windowsissa

Python 3.10 tai uudempi. Avaa PowerShell projektin kansiossa.

```powershell
$env:ADMIN_TOKEN = (python -c "import secrets; print(secrets.token_urlsafe(32))")
$env:ADMIN_TOKEN
python palvelin.py
```

Avaa http://localhost:8780. Ylläpito käyttää yllä olevaa avainta. Palstan viestejä voi ilmoittaa ketjussa. Ylläpidossa voi poistaa ilmoitettuja viestejä sekä lukita ja avata ketjuja niiden numerolla. MVP:n nimimerkit eivät ole käyttäjätilejä eikä niiden omistajuutta tarkisteta.

## Render

Pura ZIP uuteen GitHub-repositorioon. Luo siitä **Web Service** Python-ajoympäristöllä. Build Command voi olla `python -m py_compile palvelin.py keraaja.py luetuimmat.py`. Start Command on `python palvelin.py`. Health Check Path on `/health`.

- Aseta `ADMIN_TOKEN` Renderin ympäristömuuttujiin ja säilytä avain omassa tallessa.
- Pysyviä keskusteluja varten liitä palveluun pysyvä levy, liitospiste esimerkiksi `/var/data`, ja aseta `DATABASE_PATH=/var/data/keskustelu.sqlite3`. Käytä yhtä palvelininstanssia.
- Renderin ilmaisella palvelulla voi kokeilla sovellusta. Palvelu voi nukahtaa ilman liikennettä, jolloin keräys pysähtyy, ja paikallinen SQLite-tietokanta voi tyhjentyä uudelleenkäynnistyksessä tai julkaisussa.
