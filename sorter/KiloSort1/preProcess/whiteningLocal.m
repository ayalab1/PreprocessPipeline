function Wrot = whiteningLocal(CC, yc, xc, zc, nRange)
% whiteningLocal  Compute a local whitening matrix using nearest channels.
%
%   Wrot = whiteningLocal(CC, yc, xc, zc, nRange)
%
%   Channels are ranked by 3-D Euclidean distance so that probes with a
%   meaningful z-component (e.g. double-sided shanks) correctly prefer
%   geometrically close neighbours.  For 2-D probes pass zc = zeros(N,1).

Wrot = zeros(size(CC,1), size(CC,1));
for j = 1:size(CC,1)
    ds          = (xc - xc(j)).^2 + (yc - yc(j)).^2 + (zc - zc(j)).^2;
    [~, ilocal] = sort(ds, 'ascend');
    ilocal      = ilocal(1:nRange);
    
    [E, D]      = svd(CC(ilocal, ilocal));
    D           = diag(D);
    eps         = 1e-6;
    wrot0       = E * diag(1./(D + eps).^.5) * E';
    Wrot(ilocal, j)  = wrot0(:,1);
end