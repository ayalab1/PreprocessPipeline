function data = shift_data(data, dy, ycoords, xcoords, zcoords, iCovChans, sigDrift, Wrot)

shiftM = shift_matrix(dy, ycoords, xcoords, zcoords, iCovChans, sigDrift, Wrot);
data   = shiftM * data;
