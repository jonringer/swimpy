{
  description = "SWIM flake";

  inputs = {
    utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-unstable";
  };

  outputs = { self, nixpkgs, utils, ... }:
    let
      # put devShell and any other required packages into local overlay
      localOverlay = import ./nix/overlay.nix;
      overlays = [
        localOverlay
      ];

      pkgsForSystem = system: import nixpkgs {
        # if you have additional overlays, you may add them here
        overlays = [
          localOverlay # this should expose devShell
        ];
        inherit system;
      };
    # https://github.com/numtide/flake-utils#usage for more examples
    in utils.lib.eachSystem [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" ] (system: rec {
      legacyPackages = pkgsForSystem system;
      packages = utils.lib.flattenTree {
        inherit (legacyPackages) swim devShell;
      };
      defaultPackage = packages.swim;
      devShell = legacyPackages.devShell;
      apps.swim = utils.lib.swim { drv = packages.swim; };  # use as `nix run .#swim`
      checks = { inherit (legacyPackages) swim; };              # items to be ran as part of `nix flake check`
  }) // {
    # non-system suffixed items should go here
    overlays.default = localOverlay;
    overlay = nixpkgs.lib.composeManyExtensions overlays; # expose overlay which contains all dependent overlays
  };
}
