/*
Lightweight Automated Planning Toolkit
Copyright (C) 2012
Miquel Ramirez <miquel.ramirez@rmit.edu.au>
Nir Lipovetzky <nirlipo@gmail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

#ifndef __APTK_STATE__
#define __APTK_STATE__

#include <strips_prob.hxx>
#include <types.hxx>
#include <fluent.hxx>
#include <iostream>

namespace aptk
{

class Action;

class State
{
public:
	State( const STRIPS_Problem& p );
	~State();

	Fluent_Vec& fluent_vec() 		{ return m_fluent_vec; }
	Fluent_Set& fluent_set() 		{ return m_fluent_set; }
    const Value_Vec& value_vec()   const       { return m_value_vec; }
    void set_value(unsigned idx, float value){ m_value_vec[idx] = value; }
    void set_value(const Value_Vec & values);
	const Fluent_Vec& fluent_vec() const	{ return m_fluent_vec; }
	const Fluent_Set& fluent_set() const	{ return m_fluent_set; }
	
    bool value_for_var( unsigned var ) const { return m_fluent_set.isset(var); }
	void	set( unsigned f );
	void	unset( unsigned f );
	void	set( const Fluent_Vec& fv );
    void	unset( const Fluent_Vec& fv );
	void    reset();
    inline bool	entails( unsigned f ) const { return fluent_set().isset(f); }
    inline bool	entails( const State& s ) const;
    inline bool	entails( const Fluent_Vec& fv ) const;
    inline bool	entails( const Fluent_Vec& fv, unsigned& num_unsat ) const;
	size_t	hash() const;
	void	update_hash();

	State*	progress_through( const Action& a, Fluent_Vec* added = NULL, Fluent_Vec* deleted = NULL ) const;

	State*	progress_through_df( const Action& a ) const;

	State*	regress_through( const Action& a ) const;

	void    progress_lazy_state(const Action* a, Fluent_Vec* added = NULL, Fluent_Vec* deleted = NULL);

	void    regress_lazy_state(const Action* a, Fluent_Vec* added = NULL, Fluent_Vec* deleted = NULL);

	const STRIPS_Problem&		problem() const;
  
    bool operator==(const State &a) const;

	void	print( std::ostream& os ) const;

    static const bool less(const State & lhs, const State & rhs);

    std::string tostring() const;

        if (lhs.hash() < rhs.hash())
            return true;
        if (lhs.hash() > rhs.hash())
            return false;
        // hashes are the same
        // if one state vec longer than the other it is bigger
        const Fluent_Vec & lvec = lhs.fluent_vec();
        const Fluent_Vec & rvec = rhs.fluent_vec();
        assert(lvec.size() != 0);
        assert(rvec.size() != 0);
        if (lvec.size() < rvec.size())
            return true;
        if (lvec.size() > rvec.size())
            return false;
        // same size, have to sort vectors and
        // compare lexicographically
        Fluent_Vec lcopy = lvec;
        Fluent_Vec rcopy = rvec;
        std::sort(lcopy.begin(), lcopy.end());
        std::sort(rcopy.begin(), rcopy.end());
        bool result = std::lexicographical_compare(lcopy.begin(), lcopy.end(), rcopy.begin(), rcopy.end());
        return result;
    }

    std::string tostring() const;

protected:

	Fluent_Vec			m_fluent_vec;
	Fluent_Set			m_fluent_set;
    Value_Vec           m_value_vec;
	const STRIPS_Problem&		m_problem;
	size_t				m_hash;
};



inline	void State::reset(  )
{
    m_fluent_vec.clear();
    m_fluent_set.reset();
}

inline bool	State::entails( const State& s ) const
{
    return entails( s.fluent_vec() );
}

inline bool	State::entails( const Fluent_Vec& fv ) const
{
    for ( unsigned i = 0; i < fv.size(); i++ )
      if ( !fluent_set().isset(fv[i]) ) {
        return false;
      }
    return true;
}

inline bool	State::entails( const Fluent_Vec& fv, unsigned& num_unsat ) const
{
    num_unsat = 0;
    for ( unsigned i = 0; i < fv.size(); i++ )
        if ( !fluent_set().isset(fv[i]) ) num_unsat++;
    return num_unsat == 0;

}

inline	size_t State::hash() const {
    return m_hash;
}

inline bool State::operator==(const State &a) const {
    return fluent_set() == a.fluent_set();
}

inline const STRIPS_Problem& State::problem() const
{
    return m_problem;
}

inline	void State::set( unsigned f )
{
    if ( entails(f) ) return;
    m_fluent_vec.push_back( f );
    m_fluent_set.set( f );
}

inline	void State::set( const Fluent_Vec& f )
{

    for ( unsigned i = 0; i < f.size(); i++ )
    {
        if ( !entails(f[i]) )
        {
            m_fluent_vec.push_back(f[i]);
            m_fluent_set.set(f[i]);
        }
    }
}

inline	void State::unset( unsigned f )
{
    if ( !entails(f) ) return;

    for ( unsigned k = 0; k < m_fluent_vec.size(); k ++ )
        if ( m_fluent_vec[k] == f )
        {
            for ( unsigned l = k+1; l < m_fluent_vec.size(); l++ )
                m_fluent_vec[l-1] = m_fluent_vec[l];
            m_fluent_vec.resize( m_fluent_vec.size()-1 );
            break;
        }

    m_fluent_set.unset( f );
}

inline	void State::unset( const Fluent_Vec& f )
{

    for ( unsigned i = 0; i < f.size(); i++ )
    {
        if ( !entails(f[i]) )
            continue;
        for ( unsigned k = 0; k < m_fluent_vec.size(); k ++ )
            if ( m_fluent_vec[k] == f[i] )
            {
                for ( unsigned l = k+1; l < m_fluent_vec.size(); l++ )
                    m_fluent_vec[l-1] = m_fluent_vec[l];
                m_fluent_vec.resize( m_fluent_vec.size()-1 );
                break;
            }
        m_fluent_set.unset(f[i]);
    }
}

std::ostream& operator<<(std::ostream &os, State &s);

std::ostream& operator<<(std::ostream &os, const State &s);

}

#endif // State.hxx
