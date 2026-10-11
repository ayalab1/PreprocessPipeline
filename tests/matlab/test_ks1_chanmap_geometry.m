function test_ks1_chanmap_geometry
% Regression checks for row-vector 2-D maps and single double-sided shanks.
root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(root, 'sorter', 'KiloSort1', 'preProcess'));
addpath(fullfile(root, 'sorter', 'KiloSort1', 'finalPass'));
addpath(fullfile(root, 'external', 'CellExplorer', 'toolboxes', 'npy-matlb'));

CC = diag([1, 2, 3]);
xc = [0, 10, 100];
yc = [0, 0, 0];
zc = zeros(3, 1);
Wrow = whiteningLocal(CC, yc, xc, zc, 2);
Wcolumn = whiteningLocal(CC, yc(:), xc(:), zc, 2);
assert(max(abs(Wrow(:) - Wcolumn(:))) < 1e-12);
assert(Wrow(3, 3) > 0);

output = tempname;
mkdir(output);
cleanup = onCleanup(@() rmdir(output, 's'));
rez.ops = struct('Nchan', 2, 'Nfilt', 1, 'chanMap', [1; 2], ...
    'kcoords', [1; 1], 'NchanTOT', 2, 'fs', 20000, 'fbinary', 'recording.dat');
rez.st3 = [100, 1, 1];
rez.connected = true(2, 1);
rez.xcoords = [0; 0];
rez.ycoords = [0; 0];
rez.zcoords = [0; 25];
rez.sidecoords = [0; 1];
rez.U = reshape(single([1; 1]), [2, 1, 1]);
rez.W = reshape(single([1; 1; 1]), [3, 1, 1]);
rez.cProj = single(1);
rez.iNeigh = uint32(1);
rez.cProjPC = single(1);
rez.iNeighPC = uint32(1);
rez.Wrot = eye(2);

rezToPhy(rez, output);
positions = readNPY(fullfile(output, 'channel_positions.npy'));
assert(isequal(double(positions(:, 1)), [0; 25]));
assert(isequal(double(positions(:, 2)), [0; 0]));
end
