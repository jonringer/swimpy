{ mkShell
, gfortran
, python3
, stdenv
}:

mkShell rec {

  nativeBuildInputs = [
    gfortran
    (python3.withPackages (ps: with ps; [
        pip
        setuptools
        wheel
    ]))
    python3.pkgs.venvShellHook
  ];

  venvDir = ".venv${python3.passthru.pythonVersion}";

  postVenvCreation = ''
    unset SOURCE_DATE_EPOCH

    git submodule update --init dependencies/modelmanager/
    git submodule update --init dependencies/m.swim

    pip install -r dependencies/modelmanager/requirements_dev.txt

    pip install -e .
  '';

  postShellHook = ''
    git submodule update --init dependencies/modelmanager/
    git submodule update --init dependencies/m.swim
    unset SOURCE_DATE_EPOCH

    # pyinstaller downloads a precompiled c++ binary
    export LD_LIBRARY_PATH=${stdenv.cc.cc.lib}/lib
  '';
}
