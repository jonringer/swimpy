"""
SWIM input functionality.
"""
import os.path as osp
import warnings
import datetime as dt

import pandas as pd
from modelmanager.utils import propertyplugin
from modelmanager.plugins.templates import TemplatesDict
from modelmanager.plugins.pandas import ReadWriteDataFrame
from modelmanager.plugins import grass as mmgrass

from swimpy import utils, plot
import matplotlib.pyplot as plt  # after plot


@propertyplugin
class basin_parameters(TemplatesDict):
    """
    Set or get any values from the .bsn file by variable name.
    """
    template_patterns = ['input/*.bsn']


@propertyplugin
class config_parameters(TemplatesDict):
    """
    Set or get any values from the .cod or swim.conf file by variable name.
    """
    template_patterns = ['input/*.cod', 'swim.conf']

    @property
    def start_date(self):
        return dt.date(self['iyr'], 1, 1)

    @property
    def end_date(self):
        return dt.date(self['iyr']+self['nbyr']-1, 12, 31)


@propertyplugin
class subcatch_parameters(ReadWriteDataFrame):
    """
    Read or write parameters in the subcatch.prm file.
    """
    path = 'input/subcatch.prm'

    def read(self, **kwargs):
        bsn = pd.read_table(self.path, delim_whitespace=True)
        stn = 'stationID' if 'stationID' in bsn.columns else 'station'
        bsn.set_index(stn, inplace=True)
        return bsn

    def write(self, **kwargs):
        bsn = self.copy()
        bsn['stationID'] = bsn.index
        strtbl = bsn.to_string(index=False, index_names=False)
        with open(self.path, 'w') as f:
            f.write(strtbl)
        return


@propertyplugin
class subcatch_definition(ReadWriteDataFrame):
    """
    Interface to the subcatchment definition file from DataFrame or grass.
    """
    path = 'input/subcatch.def'
    plugin = ['__call__']

    def read(self, **kwargs):
        scdef = pd.read_table(self.path, delim_whitespace=True, index_col=0)
        return scdef

    def write(self, **kwargs):
        tbl = self.copy()
        tbl.insert(0, 'subbasinID', tbl.index)
        tblstr = tbl.to_string(index=False, index_names=False)
        with open(self.path, 'w') as f:
            f.write(tblstr)
        return

    def update(self, catchments=None, subbasins=None):
        """Write the definition file from the subbasins grass table.

        Arguments
        ---------
        catchments : list-like
            Catchment ids to subset the table to. Takes precedence over
            subbasins argument.
        subbasins : list-like
            Subbasin ids to subset the table to.
        """
        cols = ['subbasinID', 'catchmentID']
        tbl = mmgrass.GrassAttributeTable(self.project,
                                          vector=self.project.subbasins.vector,
                                          subset_columns=cols)
        # optionally filter
        if catchments:
            tbl = tbl[[i in catchments for i in tbl.catchmentID]]
        elif subbasins:
            tbl = tbl.filter(items=subbasins, axis=0)
        # add stationID
        scp = {v: k for k, v in
               self.project.subcatch_parameters['catchmentID'].items()}
        tbl['stationID'] = [scp[i] for i in tbl['catchmentID']]
        # save and write
        self.__call__(tbl)
        return


class climate(object):
    """All climate input related functionality."""

    def __init__(self, project):
        self.project = project
        return

    @propertyplugin
    class inputdata(ReadWriteDataFrame):
        """A lazy DataFrame representation of the two 'clim'-files.

        Rather than being read on instantiation, .read() and .write() need to
        be called explicitly since both operations are commonly time-consuming.
        """
        namepattern = 'clim%i.dat'
        variables = ['radiation', 'humidity', 'precipitation',
                     'tmin', 'tmax', 'tmean']
        clim_variables = {1: variables[:3], 2: variables[3:]}
        column_levels = ['variable', 'subbasinID']
        plugin = ['print_stats', 'plot_temperature', 'plot_precipitation']

        def __init__(self, project):
            pd.DataFrame.__init__(self)
            self.project = project
            self.path = project.config_parameters['climatedir']
            ReadWriteDataFrame.__init__(self, project)
            return

        def read(self, climdir=None, **kw):
            startyr = self.project.config_parameters['iyr']
            path = osp.join(climdir or self.path, self.namepattern)
            dfs = pd.concat([self.read_clim(path % i, startyr, vs, **kw)
                             for i, vs in self.clim_variables.items()], axis=1)
            dfs.sort_index(axis=1, inplace=True)
            return dfs

        @classmethod
        def read_clim(cls, path, startyear, variables, **readkwargs):
            """Read single clim file and return DataFrame with index and
            columns.
            """
            assert len(variables) == 3
            readargs = dict(delim_whitespace=True, header=None, skiprows=1)
            readargs.update(readkwargs)
            df = pd.read_table(path, **readargs)
            df.index = pd.PeriodIndex(start=str(startyear), periods=len(df),
                                      freq='d', name='time')
            nsub = int(len(df.columns)/3)
            df.columns = cls._create_columns(nsub, variables)
            return df

        @classmethod
        def _create_columns(cls, nsubbasins, variables):
            v = [range(1, nsubbasins+1), variables]
            ix = pd.MultiIndex.from_product(v, names=cls.column_levels[::-1])
            return ix.swaplevel()

        def write(self, outdir=None, **writekw):
            path = osp.join(outdir or self.path, self.namepattern)
            for i, vs in self.clim_variables.items():
                # enforce initial column order
                df = self[self._create_columns(int(len(self.columns)/6), vs)]
                header = ['%s_%s' % (v[:4], s) for v, s in df.columns]
                writeargs = dict(index=False, header=header)
                writeargs.update(writekw)
                with open(path % i, 'w') as f:
                    df.to_string(f, **writeargs)
            return

        def print_stats(self):
            """Print statistics for all variables."""
            stats = self.mean(axis=1, level=0).describe().round(2).to_string()
            print(stats)
            return stats

        def aggregate(self, variables=[], **kw):
            """Mean data over all subbasins and optionally subset and aggregate
            to a frequency or regime.

            Arguments
            ---------
            variables : list
                Subset variables. If empty or None, return all.
            **kw :
                Keywords to utils.aggregate_time.
            """
            vars = variables or self.variables
            subs = self[vars].mean(axis=1, level='variable')
            aggm = {v: 'sum' if v == 'precipitation' else 'mean' for v in vars}
            aggregated = utils.aggregate_time(subs, resample_method=aggm, **kw)
            return aggregated

        @plot.plot_function
        def plot_temperature(self, regime=False, freq='d', minmax=True,
                             ax=None, runs=None, output=None, **linekw):
            """Line plot of mean catchment temperature.

            Arguments
            ---------
            regime : bool
                Plot regime. freq must be 'd' or 'm'.
            freq : <pandas frequency>
                Any pandas frequency to aggregate to.
            minmax : bool
                Show min-max range.
            **kw :
                Parse any keyword to the tmean line plot function.
            """
            ax = ax or plt.gca()
            clim = self.aggregate(variables=['tmean', 'tmin', 'tmax'],
                                  freq=freq, regime=regime)
            minmax = [clim.tmin, clim.tmax] if minmax else []
            line = plot.plot_temperature_range(clim.tmean, ax, minmax=minmax,
                                               **linekw)
            if regime:
                xlabs = {'d': 'Day of year', 'm': 'Month'}
                ax.set_xlabel(xlabs[freq])
            return line

        @plot.plot_function
        def plot_precipitation(self, regime=False, freq='d',
                               ax=None, runs=None, output=None, **barkwargs):
            """Bar plot of mean catchment precipitation.

            Arguments
            ---------
            regime : bool
                Plot regime. freq must be 'd' or 'm'.
            freq : <pandas frequency>
                Any pandas frequency to aggregate to.
            **barkwargs :
                Parse any keyword to the bar plot function.
            """
            ax = ax or plt.gca()
            clim = self.aggregate(variables=['precipitation'],
                                  freq=freq, regime=regime)['precipitation']
            bars = plot.plot_precipitation_bars(clim, ax, **barkwargs)
            if regime:
                xlabs = {'d': 'Day of year', 'm': 'Month'}
                ax.set_xlabel(xlabs[freq])
            return bars


class StructureFile(ReadWriteDataFrame):
    """Read-Write plugin for the structure file.

    This is accessible via the ``hydroptes.attributes`` propertyplugin and
    placed here for consistency and reuse.
    """
    file_columns = ['subbasinID', 'landuseID', 'soilID', 'management',
                    'wetland', 'elevation', 'glacier', 'area', 'cells']

    @property
    def path(self):
        relpath = 'input/%s.str' % self.project.project_name
        return self._path if hasattr(self, '_path') else relpath

    @path.setter
    def path(self, value):
        self._path = value
        return

    def read(self, **kwargs):
        df = pd.read_table(self.path, delim_whitespace=True)
        # pandas issues UserWarning if attribute is set with Series-like
        warnings.simplefilter('ignore', UserWarning)
        self.file_header = list(df.columns)
        warnings.resetwarnings()

        nstr, nexp = len(df.columns), len(self.file_columns)
        if nexp == nstr:
            df.columns = self.file_columns
        else:
            msg = ('Non-standard column names: Found different number of '
                   'columns .str file, expecting %i, got %i: %s')
            warnings.warn(msg % (nexp, nstr, ', '.join(df.columns)))
        # get rid of last 0 line
        if df.iloc[-1, :].sum() == 0:
            df = df.iloc[:-1, :]
        df.index = list(range(1, len(df)+1))
        return df

    def write(self, **kwargs):
        with file(self.path, 'w') as f:
            self.to_string(f, index=False, header=self.file_header)
            f.write('\n'+' '.join(['0 ']*len(self.file_header)))
        return


@propertyplugin
class station_daily_discharge_observed(ReadWriteDataFrame):
    path = 'input/runoff.dat'
    subbasins = []  #: Holds subbasinIDs if the file has them
    outlet_station = []  #: Name of the first column which is always written

    def read(self, path=None, **kwargs):
        path = path or self.path
        na_values = ['NA', 'NaN', -999, -999.9, -9999]
        # first read header
        with open(path, 'r') as fi:
            colnames = fi.readline().strip().split()
            subids = fi.readline().strip().split()
        skiphead = 1
        # subbasins are given if all are ints and they are all in the subbasins
        try:
            si = pd.Series(subids, dtype=int, index=colnames)
            if list(si.iloc[1:3]) == [0, 0]:
                self.subbasins = si.iloc[3:]
                skiphead += 1
        except ValueError:
            warnings.warn('No subbasinIDs given in second row of %s' % path)
        # read entire file
        rodata = pd.read_table(path, skiprows=skiphead, header=None,
                               delim_whitespace=True, index_col=0,
                               parse_dates=[[0, 1, 2]], names=colnames,
                               na_values=na_values)
        rodata.index = rodata.index.to_period()
        self.outlet_station = rodata.columns[0]
        return rodata

    def write(self, **kwargs):
        head = 'YYYY  MM  DD  ' + '  '.join(self.columns.astype(str)) + '\n'
        if len(self.subbasins) > 0:
            sbids = '  '.join(self.subbasins.astype(str))
            head += '%s  0  0  ' % len(self.columns) + sbids + '\n'
        # write out
        out = [self.index.year, self.index.month, self.index.day]
        out += [self[s] for s in self.columns]
        out = pd.DataFrame(zip(*out))
        with open(self.path, 'w') as fo:
            fo.write(head)
            out.to_string(fo, na_rep='-9999', header=False, index=False)
        return

    def __call__(self, stations=[], start=None, end=None):
        """Write daily_discharge_observed from stations with their subbasinIDs.

        Arguments
        ---------
        stations : list-like, optional
            Stations to write to file. self.outlet_station will always be
            written as the first column.
        start, end : datetime-like, optional
            Start and end to write to. Defaults to
            project.config_parameters.start_date/end_date.
        """
        df = self._get_observed_discharge(stations=stations, start=start,
                                          end=end)
        # update subbasins
        self.subbasins = self.project.stations.loc[df.columns, 'subbasinID']
        # assign to self
        pd.DataFrame.__init__(self, df)
        self.write()
        return self

    def _get_observed_discharge(self, stations=[], start=None, end=None):
        """Get daily_discharge_observed from stations and their subbasinIDs.

        Arguments
        ---------
        stations : list-like, optional
            Stations to write to file. self.outlet_station will always be
            written as the first column.
        start, end : datetime-like, optional
            Start and end to write to. Defaults to
            project.config_parameters.start_date/end_date.
        """
        stat = [self.outlet_station]
        stat += [s for s in stations if s != self.outlet_station]
        # unpack series from dataframe, in right order!
        pstations = self.project.stations
        si = [s for s in stat if s not in pstations.index]
        assert not si, '%s not found station table: %s' % (si, pstations.index)
        satt = pstations.loc[stat]
        q = pd.DataFrame({s: satt.loc[s, 'daily_discharge_observed']
                          for s in stat})
        # change start/end
        conf = self.project.config_parameters
        q = q.truncate(before=start or conf.start_date,
                       after=end or conf.end_date)
        return q


# only import the property plugins on from output import *
__all__ = [n for n, p in globals().items() if property in p.__class__.__mro__]
__all__ += ['climate']
