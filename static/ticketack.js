/* globals django */
( function ( $ ) {
	function findParent( el, condition ) {
		while ( true ) {
			if ( el.is( condition ) ) {
				return el;
			}
			el = el.parent();
		}
	}

	function addAck( target, set ) {
		var block = findParent( target, 'li' );
		set.data( 'prev', block.html() );
		$.ajax( {
			type: 'GET',
			url: set.attr( 'data-add-handler' ),
			dataType: 'json',
			success: function ( data ) {
				block.html( data.form );
			}
		} );
	}

	function submitAck( target, set ) {
		var formData = findParent( target, 'form' ).serialize();
		$.ajax( {
			type: 'POST',
			data: formData,
			url: set.attr( 'data-add-handler' ),
			dataType: 'json',
			success: function ( data ) {
				var item = findParent( target, '.add-block' ),
					next;
				if ( data.form !== undefined ) {
					item.html( data.form );
				}
				if ( data.success ) {
					next = item.clone();
					next.html( set.data( 'prev' ) );
					item.removeClass( 'add-block' );
					item.addClass( 'newly-added' );
					item.attr( 'data-id', data.id );
					item.after( next );
				}
			}
		} );
	}

	function removeAck( target, set ) {
		var ackLine = findParent( target, 'li' ),
			block = findParent( target, '.remove-block' );
		if ( block.hasClass( 'really' ) ) {
			ackLine.addClass( 'removing' );
			$.ajax( {
				type: 'POST',
				data: { id: ackLine.attr( 'data-id' ), csrfmiddlewaretoken: set.attr( 'data-token' ) },
				url: set.attr( 'data-remove-handler' ),
				dataType: 'json',
				success: function ( data ) {
					if ( data.success ) {
						ackLine.remove();
					} else {
						ackLine.addClass( 'failed' );
					}
				}
			} );
		} else {
			block.addClass( 'really' );
		}
	}

	$( document ).ready( function () {
		$( '.ack-set' ).click( function ( event ) {
			var target = $( event.target ),
				set = $( this );
			if ( target.hasClass( 'add-ack' ) ) {
				addAck( target, set );
				return false;
			}
			if ( target.hasClass( 'submit-ack' ) ) {
				submitAck( target, set );
				return false;
			}
			if ( target.hasClass( 'remove-ack' ) ) {
				removeAck( target, set );
				return false;
			}
		} );
	} );
}( django.jQuery ) );
