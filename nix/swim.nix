{ lib
, stdenv
, gfortran
}:

stdenv.mkDerivation rec {
  pname = "swim";
  version = "git";

  src = null;
  # Directory can only exist locally
  #src = ../dependencies/swim/code;

  makeFlags = [
    # needed by cross compilation
    "FC=${stdenv.cc.targetPrefix}gfortran"
  ];

  nativeBuildInputs = [ gfortran ];

  installPhase = ''
    mkdir -p $out/bin
    mv swim $out/bin/swim
  '';

  meta = with lib; {
    description = "SWIM";
    license = licenses.mit;
  };
}
