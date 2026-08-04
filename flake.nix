{
  description = "Development environment for the door signboard";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { nixpkgs, ... }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          python = pkgs.python3.withPackages (pythonPackages: with pythonPackages; [
            numpy
            pillow
            spidev
          ]);
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.dejavu_fonts
              python
            ];

            DOOR_SIGNBOARD_FONT = "${pkgs.dejavu_fonts}/share/fonts/truetype/DejaVuSans.ttf";
            DOOR_SIGNBOARD_BOLD_FONT = "${pkgs.dejavu_fonts}/share/fonts/truetype/DejaVuSans-Bold.ttf";
          };
        });
    };
}
