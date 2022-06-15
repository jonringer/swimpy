final: prev: {
    devShell = prev.callPackage ./dev-shell.nix { };

    swim = prev.callPackage ./swim.nix { };
}
