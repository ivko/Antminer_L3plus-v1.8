opkg update
opkg install update-alternatives ca-certificates wget perl-module-feature perl-module-utf8 perl-module-base perl-module-tie-hash perl-module-file-glob perl-module-unicore
echo ca_certificate=/etc/ssl/certs/ca-certificates.crt > ~/.wgetrc
cd /usr/sbin
wget --no-check-certificate https://raw.githubusercontent.com/mvduin/bbb-pin-utils/master/show-pins
chmod a+x show-pins
