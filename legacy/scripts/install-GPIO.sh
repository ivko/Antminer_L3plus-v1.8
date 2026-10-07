# GPIO
opkg update
opkg install update-alternatives ca-certificates wget git autoconf automake libtool gcc-dev gcc-symlinks cpp-symlinks g++-symlinks binutils binutils-symlinks make tar
echo ca_certificate=/etc/ssl/certs/ca-certificates.crt > ~/.wgetrc
git config --global http.sslCAinfo /etc/ssl/certs/ca-certificates.crt
git clone https://github.com/shabaz123/iobb.git
cd iobb
rm -rf .git
find ./Demo/ -name "*.png" -exec rm {} \;
find ./Demo/ -name "*.png" -exec rm {} \;



