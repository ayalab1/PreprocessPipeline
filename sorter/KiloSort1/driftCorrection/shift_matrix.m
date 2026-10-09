function shiftM = shift_matrix(dy, ycoords, xcoords, zcoords, iCovChans, sig, Wrot)
% shift_matrix  Build a channel-interpolation matrix that shifts data by dy
%               along the probe insertion axis (y).
%
%   zcoords contributes to the Gaussian distance kernel so that channels
%   on opposite faces/shanks are correctly decoupled.  Drift is modelled
%   only along ycoords; zcoords is treated as static.

yminusy = bsxfun(@minus, ycoords - dy, ycoords').^2 + ...
    bsxfun(@minus, xcoords , xcoords').^2 + ...
    bsxfun(@minus, zcoords , zcoords').^2;

newSamp = exp(- yminusy/(2*sig^2));

shiftM = Wrot * ((newSamp * iCovChans)/Wrot);
